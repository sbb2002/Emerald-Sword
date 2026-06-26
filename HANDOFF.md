# HANDOFF — 복합모멘텀 QQQM/GLDM 봇

> 다음 세션이 이 파일만 읽고 이어받을 수 있도록 작성. 최종 업데이트: **2026-06-26**
> 완료된 작업 상세는 `DONE.md` 참조(이 파일은 현재 상태 + 할 일 + 영구 함정만).

## Goal
나스닥100(QQQM)/금(GLDM) 3·6·12개월 복합모멘텀 자동매매 봇. 명세 단일 진실 원천: `blueprints/PRD_momentum_bot.md`. 소스 `./src`, 테스트 `./tests`. Phase A/B/C 구현·테스트 완료(현재 **126 passed, 1 skipped**). Render 배포 + KIS 모의계좌 라이브 운용 중 — 지금은 라이브 안정화 단계.

---

## 🟢 현재 상태 (2026-06-26 장마감 후 기준)

- `/emergency-stop` 청산 + `/resume` **완료**. 현재 **현금 100% = $100,000(시드 전액)**, `is_paused=False`, 신호 **NASDAQ**, **보유 없음**. → 출발점이 이미 깨끗함.
- estop 토큰 분당제한 버그는 `f23a7ce` 로 수정·배포됨(`_on_estop_challenge` 에서 NAV 조회 제거).
- ⚠️ 단, 이날 검증은 전부 **장외(미 증시 마감 후)** 라 정작 검증하려던 (a)·#1 은 **둘 다 미완**(아래 "장중 검증" 참조). 장외에선 매도 지정가가 접수만 되고 미체결로 떠 cron 이 중간 포지션을 보유로 오판함(자가치유로 결국 정리되니 위험은 아님).

## ✅ 다음 세션: 장중에 바로 이 순서로 검증 진행

> **반드시 미 증시 정규장(= KST 밤 22:30 ~ 익일 05:00, 6월 서머타임 기준)** 에 실행. 장외면 지정가가 즉시 체결 안 돼 정산 타이밍·NAV 보고가 왜곡된다. 각 단계 사이 + 직전 KIS 호출과 **1~2분 텀**(토큰 분당 제한).

1. **cron 수동 실행** — `python -m src.cron`
   - 현금 100% + 신호 NASDAQ → **QQQM ~335주 매수**(보유 생성). (현금 상태라 `_already_at_target=False` → 이번엔 매수 실행됨.)
   - ✅ **확인 (a) NAV 병기 첫 라이브 검증**: 텔레그램 사후보고에 `총자산 $… → $…` / `현금 $… → $…` **2줄**이 뜨는지. `/log` 에 `@체결가 · 총자산 …·현금 …` 형식인지. → **이 메시지를 캡처해 보고할 것.**
2. **verify_switch** — `python -m src.verify_switch`
   - QQQM 100% 보유 상태에서 QQQM↔GLDM 왕복 전환. 끝나면 원위치(QQQM) 복귀.
   - ✅ **확인 #1 정산 타이밍**: 두 전환 평가비중이 모두 **≥95% → 정상(무조치)**. 한 번이라도 95% 미만이면 매도대금 미반영 → `strategy_cycle` 매수 leg 전 정산 대기/매수여력 재폴링 보강(아래 #1 상세 참조). **결과 보고 전까지 방어 코드 넣지 말 것.**
3. **(선택) emergency-stop → resume** — QQQM 보유 상태에서 장중 emergency-stop 이 **즉시 체결로 청산**되는지 확인(이번엔 장외라 미체결로 헷갈렸음). 확인 후 `/resume`.

> emergency-stop 은 "출발점"이 아니라 **보유가 있을 때 맨 끝에** 검증. 현금 상태에서 호출하면 "청산할 보유 종목 없음"만 뜬다.

---

## 배포 상태
- **`main` = 배포 브랜치**(Render autoDeploy). 다른 머신: `git checkout main && git pull`.
- Render: web=free(유휴 spin-down, keep-alive 미사용), cron=starter(유료, 월 1회). webhook=`https://<host>/webhook/<BOT_TOKEN>`.
- KIS **모의계좌**(CANO 50162185-01, `ACNT_PRDT_CD=01`). 시드 **$100,000 USD**, 매수 시 자동환전. 해외주식 모의투자 '리그' 신청 필수.
- 비밀값은 전부 Render 환경변수(`.env.example` 참고). 거래종목 QQQM/GLDM 고정, 정수 주문, 기본 모드 `virtual`.
- 로깅: `src/logging_setup.py`(stdout INFO) — KIS 호출/주문/잔고 전부 로그.

---

## 🚧 배경 상세 · 추가 할 일

> 위 "장중 검증" 1~2번의 근거. 3번 이하는 검증 결과에 따라 우선순위 결정.

### 1. 월말 전환(QQQM↔GLDM) 매도→매수 정산 타이밍 — 모의 라이브 검증 (미검증 위험)
- **위험**: `order_executor.execute()` 는 한 사이클에서 매도(`place_order SELL`, '접수'만) → 1.1s → 매수(`get_buyable_qty`=KIS `max_ord_psbl_qty` 기준)로 이어진다. KIS 가 미체결 매도대금을 같은 사이클의 `max_ord_psbl_qty` 에 즉시 반영하지 않으면 신규 종목이 **과소 매수**된다. 최악은 현금 ~$0 인 100% 보유에서 **0주 매수 → 매도만 되고 전환이 깨짐**. `fill_monitor` 도 '접수' 기준이라 보정 못 함. **정기 월말 사이클은 이 시나리오를 한 번도 안 거침**(6/16 라이브는 매도·매수가 4분 간격 별도 트리거 — 같은 사이클 아님).
- **검증 도구**: `src/verify_switch.py`(모의 전용). `python -m src.verify_switch` 로 현재 보유 종목의 반대로 전환했다가 원위치 복구하며, 각 전환 직후/+3s 의 보유·현금·총자산·**매수여력**·타겟 **평가비중(%)** 출력. `trading_mode=real` 이면 거부. cron 과 1~2분 텀 둘 것. **단일 종목 100% 보유(정상 운용) 상태에서 실행**해야 매도→매수가 관찰됨. ⚠️ 위 긴급 청산이 끝나 현금/일부보유 상태면 먼저 한 종목 100% 보유로 복귀시킨 뒤 실행.
- **판정**: 두 전환 평가비중이 모두 **≥95%면 정산 즉시 반영 = 무조치**. 한 번이라도 95% 미만(현금 다량 잔여)이면 매도대금 미반영 → 후속조치로 `strategy_cycle` 매수 leg 전에 정산 대기/매수여력 재폴링(또는 매도 체결 확인) 보강. **결과 보고 전까지 방어 코드는 넣지 않음**(과설계 방지).

### 2. 부분체결 실제 빈도 관찰 — 배포 후 라이브 관찰 (코딩 아님)
- 장중 트리거 후 텔레그램 보고에 ⚠️(부분체결)이 뜨는지 확인.
- `after` 스냅샷이 주문 직후 찍혀 체결이 늦게 잡힐 수 있음. 빈번하면 `src/strategy_cycle.py` step 8 전 1~2초 지연 추가.
- 관련 파일: `src/strategy_cycle.py` → `run_cycle()` step 8, `_format_report()`, `_leg_filled()`.

### 3. (선택) `get_executions` 실구현 → 부분체결 자동추격 복원
- 현재 `KisClient.get_executions` 는 스텁(0 반환)이라 fill_monitor 재주문이 비활성화돼 있음(중복 매수 방지). KIS 체결조회(`inquire-ccnl`)로 실구현하면 '대기 → 체결확인 → 미체결분 취소 후 재주문'을 안전하게 복원 가능. 위 #1/#2 결과에 따라 우선순위 결정.

---

## ⚠️ 영구 주의사항 (함정 — 건드리기 전에 반드시 읽을 것)
- **한 명령 처리에서 KIS 클라이언트(토큰 발급)는 1회만**: `web.py` `_kis()` 는 호출마다 새 인스턴스(토큰 없음)를 만든다. 한 명령에서 KIS 호출이 필요한 콜러블(`nav_provider`·`liquidator` 등)을 2개 이상 부르면 각자 토큰을 발급 → 두 번째가 **분당 제한(403)** 에 걸려 실패한다. 2026-06-26 `/emergency-stop` 가 이걸로 청산 실패함. 새 명령 핸들러에서 KIS 를 2번 이상 거치게 만들지 말 것.
- **KIS 토큰 1분 제한**: web 명령 직후 1분 내 cron 트리거가 겹쳐도 403. 라이브 검증·트리거는 1~2분 텀 유지.
- **KIS `ORD_DVSN` 필수**: 누락 시 `IGW00019`. 미국주식 정규장 시장가 미지원 → `ORD_DVSN="00"` + 현재가 지정가. 지정가 단가를 현재가보다 올리면 주문총액이 가용현금 초과 → 수량초과 거부.
- **`fill_monitor` 부분체결 재주문 비활성화 유지**: `get_executions` 스텁(0 반환)인 상태에서 재활성화하면 접수된 주문을 미체결로 오판해 **중복 매수**(의도의 2배)를 낸다. 실구현 전까지 재활성화 금지.
- **Telegram webhook 재전송**: 응답이 느리면(cold-start + 다중 KIS 호출) 같은 `update_id` 재전송 → 중복 처리. `processed_updates` claim 으로 멱등 처리됨. 새 webhook 핸들러 추가 시 동일 게이트를 거치게 할 것.
- **거래일 게이트는 UTC 기준 유지**: `run_cycle` step 1.5 `is_trading_day(deps.now().date())` 는 서버 UTC. cron UTC 15:30 = 미 동부 장중이라 UTC date == ET 거래일. KST/tz-aware 로 바꾸면 하루 어긋나 정상 거래일을 스킵함.
- **잔고/NAV 의 '현금' 정의**: `get_cash()`=`ord_psbl_frcr_amt`(주문가능 외화현금, USD)만이다. 원화 자동환전 모의계좌에선 환전 전 원화 매수여력이 빠져 총자산보다 작게 보인다 → `/log`·`/status` 는 총자산(NAV=보유 평가금액+현금)을 함께 표시(`DONE.md` 2026-06-26 (a) 참조).

---

## 환경/실행 메모
- 테스트: 레포 루트에서 `python -m pytest` → **126 passed, 1 skipped**. (외부 패키지 없이 실행 — httpx/psycopg는 엔트리포인트에서만 import.)
- 커밋 트레일러: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- 마이그레이션은 web/cron 시작 시 자동 적용(`src/migrate.py`). 수동: `python -m src.migrate`. 최신 = `004_trade_nav.sql`.
- 작업 방식: GitHub 이슈 단위 `/combo-run`(pre-flight → 구현 → syntax-gate → post-patch → 커밋).
