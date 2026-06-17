# HANDOFF — 복합모멘텀 QQQM/GLDM 봇

> 다음 세션이 이 파일만 읽고 이어받을 수 있도록 작성. 최종 업데이트: 2026-06-17

## Goal
나스닥100(QQQM)/금(GLDM) 3·6·12개월 복합모멘텀 자동매매 봇 구현. 명세 단일 진실 원천: `blueprints/PRD_momentum_bot.md`. 작업 방식: GitHub 이슈 단위 `/combo-run`(pre-flight → 구현 → syntax-gate → post-patch → 커밋), 소스는 `./src`, 이슈별 커밋 + Phase별 PR.

---

## ⚡ 현재 상태 (2026-06-17 갱신)

> Phase A/B/C 구현·테스트 완료(**87 passed, 1 skipped**). Render 배포 + KIS 모의계좌로 실제 매수까지 성공. 현재는 라이브 안정화 단계.

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

### 🚧 다음 세션에서 할 일 (우선순위 순)

#### 1. `/status` 중복 출력 버그 — **최우선**
- 증상: `/status` 1회 입력 시 텔레그램 메시지가 2개 출력됨.
- 의심 원인: (a) Telegram이 같은 update를 webhook에 2회 전송하거나, (b) `web.py`가 `send_message`를 2회 호출. 로그로 `update_id` 중복 여부 확인이 첫 단계.
- 확인 방법: Render 대시보드 → web 로그 → `/status` 입력 시 `update_id` 값이 2번 찍히는지.
- 관련 파일: `src/web.py`(webhook 핸들러), `src/commands.py`(CommandRouter), `src/telegram_bot.py`

#### 2. 부분체결 실제 빈도 관찰
- 장중 트리거 후 텔레그램 보고에 ⚠️(부분체결)이 뜨는지 확인.
- `after` 스냅샷이 주문 직후 찍혀 체결이 늦게 잡힐 수 있음. 빈번하면 `src/strategy_cycle.py` 8단계 전 1~2초 지연 추가.
- 관련 파일: `src/strategy_cycle.py` → `run_cycle()` step 8, `_format_report()`, `_leg_filled()`.

#### 3. `/status` 원화+달러 둘 다 표시 (낮음)
- psamount 응답에 `exrt`(환율)·`ord_psbl_frcr_amt`(USD 주문가능금액) 있음.
- 현재: `$100,000.00` → 목표: `$100,000.00 (₩151,000,000)` 형태.
- 관련 파일: `src/kis_client.py`(`get_cash` → exrt 함께 반환 또는 별도 `get_exrt()`), `src/commands.py`(`/status` 핸들러)

#### 4. DST·월말 거래일 게이트 (낮음)
- 현재 cron 스케줄 `30 15 28-31 * *`(UTC) = KST 00:30, 매월 28~31일. 근사치라 DST·휴장일 미반영.
- 구현 방향: `strategy_cycle.run_cycle` 진입 시 당일이 미국 주식 거래일인지 체크(pytz + pandas_market_calendars 또는 간단 테이블). 거래일 아니면 "비거래일 — 스킵" 알림 후 종료.

#### 5. `/log` 체결가·잔고변화 표시 (낮음)
- 현재 `/log`는 side/qty/signal만 보여줌. `state_store.read_trades()`가 이미 `TradeRecord`를 반환.
- 추가 목표: 체결가(after.holdings × 추정단가), 잔고 변화 (`balance_before`→`balance_after`).

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
- **PowerShell + gh**: `--body`에 한글/따옴표 → `--body-file` 사용.
- **PowerShell `2>&1` on native exe**: stderr 에러 래핑 → 리다이렉트 쓰지 말 것.
- **KIS `ORD_DVSN` 필수**: 누락 시 `IGW00019`. 미국주식 정규장 시장가 미지원 → `ORD_DVSN="00"` + 현재가 지정가.
- **KIS 토큰 1분 제한**: web↔cron 동시 호출 시 403. 1~2분 텀 필수.
- **fill_monitor 재주문**: 중복 매수 원인이었음 — 현재 비활성화, `get_executions` 실구현 전까지 재활성화 금지.

## 환경/실행 메모
- 현재 브랜치: `fix/fill-report`(origin/main에 푸시 완료). 다른 머신: `git checkout main && git pull`.
- 테스트: 레포 루트에서 `python -m pytest` → **87 passed, 1 skipped**.
- 비밀값은 전부 Render 환경변수(`.env.example` 참고). 거래종목 QQQM/GLDM 고정, 정수 주문, 기본 모드 `virtual`.
- 커밋 트레일러: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
