# HANDOFF — 복합모멘텀 QQQM/GLDM 봇

> 다음 세션이 이 파일만 읽고 이어받을 수 있도록 작성. 최종 업데이트: **2026-06-27**
> 완료된 작업 상세는 `DONE.md` 참조(이 파일은 현재 상태 + 할 일 + 영구 함정만).

## Goal
나스닥100(QQQM)/금(GLDM) 3·6·12개월 복합모멘텀 자동매매 봇. 명세 단일 진실 원천: `blueprints/PRD_momentum_bot.md`. 소스 `./src`, 테스트 `./tests`. Phase A/B/C 구현·테스트 완료(현재 **126 passed, 1 skipped**). Render 배포 + KIS 모의계좌 라이브 운용 중 — 지금은 라이브 안정화 단계.

---

## 🟢 현재 상태 (2026-06-27 장중 기준)

- 모의계좌: QQQM 214주 + 현금 ~$65 = 총자산 ~$62,900. verify_switch 부산물로 시드 감소(실전 무관).
- `feature/defence-logic` 브랜치: 정산 대기 폴링 + cron UTC now 주입 구현 완료(`765ca8a`). **main 머지·배포 대기 중**.
- 신호 NASDAQ, `is_paused=False`.

## ✅ 다음 세션: 할 일

1. **feature/defence-logic → main 머지 후 배포** (Render autoDeploy).
2. **(선택) 부분체결 빈도 관찰** — 장중 트리거 후 텔레그램 보고에 ⚠️(부분체결)이 뜨는지. 빈번하면 `strategy_cycle` step 8 전 1~2초 지연.
3. **(선택) `get_executions` 실구현** — `KisClient.get_executions`를 KIS `inquire-ccnl`로 구현해 `fill_monitor` 부분체결 재주문 복원.

## 🤔 실거래 전환 보류 중 (2026-06-27)

사용자가 실거래 전환 전에 전략 자체를 재검토 중. 핵심 쟁점:

- **목표**: CAGR 극대화, MDD 무관심, 한번 돌리고 방치.
- **백테스트**: 2004~2026 기준 CAGR 18%. 그러나 이 기간은 나스닥 독주·금융위기·AI 랠리 등 이 전략에 구조적으로 유리한 환경이 겹쳤음.
- **쟁점**: "CAGR 극대화 + MDD 무관심 + 방치"라면 현금·GLDM 보유 구간이 순수 기회비용. 단순 QQQM B&H(CAGR ~16~17%)와 차이가 1~2%p 수준이라 파라미터 오버피팅인지 진짜 알파인지 불분명.
- **결론 미정**: 사용자가 고민 중. 다음 세션에서 방향 확인 후 실거래 전환 또는 전략 재검토 진행.

---

## 배포 상태
- **`main` = 배포 브랜치**(Render autoDeploy). 다른 머신: `git checkout main && git pull`.
- Render: web=free(유휴 spin-down, keep-alive 미사용), cron=starter(유료, 월 1회). webhook=`https://<host>/webhook/<BOT_TOKEN>`.
- KIS **모의계좌**(CANO 50162185-01, `ACNT_PRDT_CD=01`). 시드 **$100,000 USD**, 매수 시 자동환전. 해외주식 모의투자 '리그' 신청 필수.
- 비밀값은 전부 Render 환경변수(`.env.example` 참고). 거래종목 QQQM/GLDM 고정, 정수 주문, 기본 모드 `virtual`.
- 로깅: `src/logging_setup.py`(stdout INFO) — KIS 호출/주문/잔고 전부 로그.

---

## 🚧 배경 상세 · 추가 할 일

### 1. 월말 전환 정산 타이밍 — ✅ 검증 완료, 방어 코드 구현됨 (`765ca8a`)
- **결과**: `sll_ruse_psbl_amt` = 매도 직후 즉시 재사용 가능 금액은 전체의 **~30%** 뿐. 70%는 정산 대기.
- **방어**: `order_executor._wait_settlement()` — 매도 후 `sll_ruse_psbl_amt == 0` 폴링(최대 120s). `feature/defence-logic` 브랜치, 미배포.

### 2. 부분체결 실제 빈도 관찰 — 배포 후 라이브 관찰 (코딩 아님)
- 장중 트리거 후 텔레그램 보고에 ⚠️(부분체결)이 뜨는지 확인.
- 빈번하면 `src/strategy_cycle.py` step 8 전 1~2초 지연 추가.

### 3. (선택) `get_executions` 실구현 → 부분체결 자동추격 복원
- 현재 `KisClient.get_executions` 는 스텁(0 반환)이라 fill_monitor 재주문이 비활성화됨(중복 매수 방지). KIS `inquire-ccnl`로 실구현하면 복원 가능.

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
