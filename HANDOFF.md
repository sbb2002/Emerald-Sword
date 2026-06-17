# HANDOFF — 복합모멘텀 QQQM/GLDM 봇

> 다음 세션이 이 파일만 읽고 이어받을 수 있도록 작성. 최종 업데이트: 2026-06-17

## Goal
나스닥100(QQQM)/금(GLDM) 3·6·12개월 복합모멘텀 자동매매 봇 구현. 명세 단일 진실 원천: `blueprints/PRD_momentum_bot.md`. 작업 방식: GitHub 이슈 단위 `/combo-run`(pre-flight → 구현 → syntax-gate → post-patch → 커밋), 소스는 `./src`, 이슈별 커밋 + Phase별 PR.

---

## ⚡ 현재 상태 (2026-06-17 갱신)

> Phase A/B/C 구현·테스트 완료(**122 passed, 1 skipped**). Render 배포 + KIS 모의계좌로 실제 매수까지 성공. 현재는 라이브 안정화 + 후속 개선 단계.

### 배포 상태
- **`main` = 배포 브랜치**(autoDeploy). 다른 머신: `git checkout main && git pull` 후 main 기준 작업.
- Render: web=free(유휴 spin-down, keep-alive 미사용), cron=starter(유료, 월 1회). webhook=`https://<host>/webhook/<BOT_TOKEN>`.
- KIS **모의계좌**(CANO 50162185-01, `ACNT_PRDT_CD=01`). 시드 **$100,000 USD**, 매수 시 자동환전. 해외주식 모의투자 '리그' 신청 필수.
- 로깅: `src/logging_setup.py`(stdout INFO). KIS 호출/주문/잔고 전부 로그.

### ✅ 라이브 검증 완료 (2026-06-16~17)
- KIS 모의 **매수 주문 성공**: BUY QQQM 324주 → `rt_cd=0 ODNO=0000035310`. 중복 차단 확인.
- 시세 EXCD 3자리(`NAS`/`AMS`)·주문/잔고 4자리(`NASD`/`AMEX`), 월봉 `GUBN=2` (`d9fe24f`)
- throttle 1.1s + 5xx 재시도 (`527cf90`), 현금=`inquire-psamount.ord_psbl_frcr_amt` (`82a34c8`)
- 매수수량=`max_ord_psbl_qty` (`9859f7a`), 자가치유 판단 + /status 강화 (`8404b7a`)
- 주문구분 `ORD_DVSN="00"` + 현재가 지정가 (`756cab7`)
- 중복매수 차단 — fill_monitor 접수 기준 정산 + 재주문 비활성화 (`be1bc5f`)
- **사후 보고 실체결 기반** — 부분체결 정직 보고 (`87a3dee`)

### 🔧 이번 세션 수정 (2026-06-17) — 배포 후 라이브 검증 필요

- **`/status` 중복 출력 버그 해결** — webhook 멱등성 도입.
  - 원인: Telegram 은 webhook 응답이 느리면(Render free cold-start + `/status` 의 다중 KIS 호출 throttle) **같은 `update_id` 를 재전송** → 재전송분이 별도 요청으로 다시 처리되어 메시지 2개. (코드가 `send_message` 를 2번 부르는 게 아님 — 코드상 배제.)
  - 수정: `update_id` 를 1회만 통과시키는 claim 게이트.
    - `src/migrations/002_processed_updates.sql` — `processed_updates(update_id PK)` 테이블.
    - `StateStore.claim_update(update_id)` — `INSERT ... ON CONFLICT DO NOTHING` + `rowcount` 으로 원자적 판정(동시 재시도까지 1회).
    - `TelegramBot.handle_update` — 인증·라우터 통과 후 claim, 중복이면 `False` 반환(무시).
  - 설계 메모: Render free 는 "200 먼저 응답 후 백그라운드 처리"가 spin-down 으로 작업이 죽을 위험 → **동기 처리 유지 + DB dedup** 선택. 다중턴 흐름(/pause→y, /real→코드)은 각 턴이 별개 update_id 라 영향 없음.
  - 테스트: `test_telegram_auth.py` 에 중복 1회 처리 / 서로 다른 update 통과 / update_id 없는 폴백 3건 추가.
  - **남은 검증**: 배포 후 실제로 `/status` 가 1개만 오는지 확인. (안 되면 Render web 로그에서 동일 `update_id` 재수신 여부 → claim 이 호출되는지 확인)

- **후속 개선 3건** — 병렬 worktree 에이전트로 구현(`708002c`·`0ac80fe`·`9799af8`), 통합 후 **105 passed, 1 skipped**.
  - `/status` 원화 병기: `kis_client.get_exrt()`(inquire-psamount `exrt`) + `StatusView.exrt` → `$100,000.00 (₩151,000,000)`. 환율 0/없으면 USD만(폴백). `get_cash()` 반환 타입 불변.
  - `/log` 체결가·잔고변화: `TradeRecord`에 `fill_price`·`balance_before`·`balance_after` 추가 + `read_trades` SELECT 확장. 값 없으면 생략(**표시 계층만** — `record_trade` 의 fill_price 저장은 미구현이라 현재 체결가는 항상 NULL → 표시 안 됨. 잔고변화는 이미 저장되어 표시됨).
  - 거래일 게이트: 신규 `src/trading_calendar.py`(외부 의존성 0, `is_trading_day`, 미 증시 휴장일 2026~2030). `run_cycle` step 1.5 에서 비거래일이면 토큰 발급 전 스킵(`NON_TRADING_DAY`). ⚠️ `deps.now()`=서버 UTC 기준 판정(cron UTC 15:30 = 미 동부 장중이라 UTC date == ET 거래일). KST/tz-aware 로 바꾸면 하루 어긋나니 금지.

- **수익률 표시** — TWR/CAGR/보유 평가손익률 + 입출금 기록. 통합 후 **122 passed, 1 skipped**.
  - 왜 TWR: 자금을 주기적으로 추가하는 운용이라 단순누적/CAGR은 입금 타이밍에 왜곡됨 → 시간가중수익률(TWR)로 전략 성과 측정(입출금 0인 현재는 단순누적과 동일).
  - `src/returns.py`(순수 함수): `compute_twr`(입출금 시점 `nav_before` 로 구간 분할) · `compute_cagr`(운용 365일 미만 None) · `running_days`.
  - `src/migrations/003_cash_flows.sql`: `cash_flows`(mode별) + 모의 시드 $100k(nav_before=0). `StateStore.record_cash_flow`/`read_cash_flows`.
  - `/deposit N`·`/withdraw N` — **`/help` 에 노출하지 않는 '숨은 명령'**(평상시 쓸 일 없어 도움말에서 제외, 동작은 정상). 현재 NAV 조회 → 확인(y/n) → 기록(실제 송금이 아니라 수익률 기준점). **실전 전환 후 자금 추가 시에만** 사용. `web.py` 가 `nav_provider` 주입. ※ 명령 자체는 `commands.py` `_command` 디스패치에 살아 있음.
  - `/status`: 보유 줄에 평가손익률 병기 + `수익률(TWR)` + `CAGR`(1년 미만은 '운용 N개월' 안내).
  - **남은 검증**: ① `kis_client.get_position_pnl`(evlu_pfls_rt 필드명/부호) 라이브 확인 — 실패 시 보유 평가손익률만 생략(나머지 정상). ② 마이그레이션 003 자동 적용(시드 1행 삽입). ③ 시드 `occurred_at`=배포 시점이라 CAGR 운용연수가 근사 — 정확한 시드일은 DB 에서 수정 가능(어차피 1년 전까진 CAGR 숨김).

### 🚧 다음 세션에서 할 일

#### 1. 부분체결 실제 빈도 관찰 — 배포 후 라이브 관찰 (코딩 아님)
- 장중 트리거 후 텔레그램 보고에 ⚠️(부분체결)이 뜨는지 확인.
- `after` 스냅샷이 주문 직후 찍혀 체결이 늦게 잡힐 수 있음. 빈번하면 `src/strategy_cycle.py` step 8 전 1~2초 지연 추가.
- 관련 파일: `src/strategy_cycle.py` → `run_cycle()` step 8, `_format_report()`, `_leg_filled()`.

#### 2. (선택) `/log` 체결가 실제 저장
- 현재 체결가(`fill_price`)는 DB에 저장되지 않아 `/log`에서 항상 생략됨(표시 로직은 이미 있음).
- 저장하려면 `strategy_cycle.run_cycle` step 8 의 `record_trade(...)` 에 `fill_price` 전달 + `state_store.record_trade`/INSERT 에 컬럼 추가 필요(체결가는 `_format_report` 가 추정하는 값과 동일 출처).

> 직전 #2(/status 원화)·#3(거래일 게이트)·#4(/log 표시 계층)는 이번 세션에 완료 → 위 "이번 세션 수정" 참고.

### 주의 (현 상태)
- **토큰 403 Forbidden**: web 명령(/status·/emergency-stop) 직후 1분 내 cron 트리거 겹치면 발생. 1~2분 텀 유지.
- **`fill_monitor` 부분체결 재시도 비활성화** 상태. `get_executions`는 스텁(0 반환). 부분체결 자동추격 없이 감지+보고만 함. (의도된 설계 — 추후 빈도 모니터링 후 결정)
- 깨끗한 재검증 시: `/emergency-stop`(청산, 자동 pause됨) → `/resume` → 트리거(명령↔트리거 1~2분 텀).

---

## Current Progress

### ✅ Phase A (워킹 스켈레톤) — PR #15 (`phase-a/skeleton` → `main`)
이슈 #1 구현. 2서비스 Blueprint(`render.yaml`), Neon 스키마+자동 마이그레이션, 텔레그램 배선(`/help`·인증게이트·모드태그), `/healthcheck`, Cron 스텁.

### ✅ Phase B (전략 엔진 전체, #3–#10) — PR #16
| 이슈 | 모듈 | 핵심 |
|---|---|---|
| #3 | `momentum.py` | 순수 함수 신호 산출, 동률 NASDAQ 우선 |
| #4 | `token_manager.py`·`position_service.py`·`kis_interface.py`·`kis_client.py` | 토큰 1회 재사용, 무캐시 잔고, KIS 인터페이스 격리 |
| #5 | `market_data.py` | 월말=각 달 마지막 거래일(결측 폴백), 이상치 ±50% |
| #6 | `order_executor.py` | 2-leg, 멱등성, floor 정수, 모드 분기 |
| #7 | `fill_monitor.py` | 접수 기준 정산 + 재주문 비활성화(중복 매수 방지) |
| #9 | `approval_manager.py` | 7일·재요청 상태기계 |
| #10 | `fallback_controller.py` | 서버6h/휴장2h×3/잔고부족 |
| #8 | `strategy_cycle.py`·`cron.py` | is_paused→신호→실체결 보고 |

### ✅ Phase C (텔레그램 명령, #11–#14)
| 이슈 | 명령 |
|---|---|
| #11 | `/status`·`/signal`·`/log` — CommandRouter(DI) |
| #12 | `/pause`·`/resume` — 펜딩 상태머신 |
| #13 | `/virtual`·`/real` — 챌린지 코드 |
| #14 | `/emergency-stop` — early-pause + 청산 |

## What Worked
- **인터페이스 격리**: httpx/psycopg를 엔트리포인트에서만 import → pytest가 외부 패키지 없이 실행됨.
- **오케스트레이션 분리**: `strategy_cycle.run_cycle(deps)` → mock 통합 테스트.
- **스택 브랜치**: Phase별 PR diff를 해당 Phase 파일로만 한정.
- **KIS 라이브 디버깅 방식**: 로그 → 트리거 → 원인 확정 → 수정 → push 사이클.

## What Didn't Work / 주의
- **KIS `ORD_DVSN` 필수**: 누락 시 `IGW00019`. 미국주식 정규장 시장가 미지원 → `ORD_DVSN="00"` + 현재가 지정가.
- **KIS 토큰 1분 제한**: web↔cron 동시 호출 시 403. 1~2분 텀 필수.
- **fill_monitor 재주문**: 중복 매수 원인이었음 — 현재 비활성화, `get_executions` 실구현 전까지 재활성화 금지.
- **Telegram webhook 재전송**: 응답이 느리면(cold-start + 다중 KIS 호출) 같은 `update_id` 를 재전송 → 중복 처리. `processed_updates` claim 으로 멱등 처리(이번 세션 수정). 새 webhook 핸들러 추가 시 동일 게이트를 거치게 할 것.

## 환경/실행 메모
- 현재 브랜치: `fix/fill-report`(origin/main에 푸시 완료). 다른 머신: `git checkout main && git pull`.
- 테스트: 레포 루트에서 `python -m pytest` → **122 passed, 1 skipped**.
- 비밀값은 전부 Render 환경변수(`.env.example` 참고). 거래종목 QQQM/GLDM 고정, 정수 주문, 기본 모드 `virtual`.
- 커밋 트레일러: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
