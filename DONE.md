# DONE — 완료 작업 아카이브 (복합모멘텀 QQQM/GLDM 봇)

> HANDOFF.md 에서 완료된 항목을 이관한 기록. 진행 중·할 일은 HANDOFF.md 참조.
> 최신 항목이 위로 오도록 날짜 역순으로 쌓는다.

---

## 2026-06-26 세션

### ✅ (a) `/log`·사후보고에 총자산(NAV) + 현금 병기 — `a9bad16`
- **문제**: `/log`·사후보고의 "잔고"가 `get_cash()`=`ord_psbl_frcr_amt`(주문가능 외화현금, USD)만이라, 원화 자동환전 모의계좌에서 환전 전 원화 매수여력이 빠져 총자산과 어긋나 보였다(매수 후 "잔고 $99,382→$67,499"인데 실제 총자산 ~$98,380).
- **수정**: 통화 모호성 없는 총자산(NAV=보유 평가금액+현금)을 별도 기록해 함께 표시.
  - `migration 004_trade_nav.sql`: `trade_log` 에 `nav_before`/`nav_after` 추가(소급 NULL → 표시 생략).
  - `PositionService.value_holdings()`/`nav()`: NAV 평가 로직 단일화(`web.py` 중복 제거).
  - `strategy_cycle`: 월말 거래 전후 NAV 기록 + 사후보고 '총자산·현금' 2줄.
  - `/log`: '잔고' 라벨 → '총자산 …·현금 …'. 기존 행은 NAV NULL 이라 현금만(라벨만 정직해짐).
- **한계**: `nav_after` 는 기존 `balance_after` 와 동일하게 주문 접수 직후 스냅샷 → 부분체결·정산 지연 시 근사.

### ✅ `/emergency-stop` 청산 실패 회귀 수정 — `f23a7ce`
- **원인**: (a) 에서 청산 전후 NAV 캡처(`nav_provider`)를 넣었는데, `nav_provider` 가 새 KIS 클라이언트로 토큰을 발급하고 이어지는 `liquidator` 도 또 다른 클라이언트로 토큰을 발급 → 두 번째(청산용)가 KIS **토큰 분당 1회 제한(403)** 에 걸려 청산 자체가 실패. (라이브 로그 2026-06-26: 토큰 발급 06:58:35 → 06:58:44 두 번 → "청산 주문 중 오류".)
- **수정**: 안전 최우선 경로라 부가기능(NAV 로그)보다 청산 성공 우선 → `_on_estop_challenge` 에서 NAV 캡처 제거. 월말 거래(`strategy_cycle`)의 NAV 로그는 cron 단일 토큰이라 영향 없음.
- **남긴 교훈**: HANDOFF '영구 주의사항'의 "한 명령 처리에서 KIS 토큰은 1회만" 참조.

### ✅ (b 도구) 월말 전환 정산 타이밍 검증 스크립트 추가 — `a3f5b39`
- `src/verify_switch.py`(모의 전용) 추가. **검증 실행 자체는 미완 → HANDOFF 할 일 참조.**

---

## 2026-06-16 ~ 06-18 (라이브 안정화 + 후속 개선)

### ✅ 라이브 검증 완료 (KIS 모의계좌)
- KIS 모의 **매수 주문 성공**: BUY QQQM 324주 → `rt_cd=0 ODNO=0000035310`. 중복 차단 확인.
- 시세 EXCD 3자리(`NAS`/`AMS`)·주문/잔고 4자리(`NASD`/`AMEX`), 월봉 `GUBN=2` (`d9fe24f`)
- throttle 1.1s + 5xx 재시도 (`527cf90`), 현금=`inquire-psamount.ord_psbl_frcr_amt` (`82a34c8`)
- 매수수량=`max_ord_psbl_qty` (`9859f7a`), 자가치유 판단 + /status 강화 (`8404b7a`)
- 주문구분 `ORD_DVSN="00"` + 현재가 지정가 (`756cab7`)
- 중복매수 차단 — fill_monitor 접수 기준 정산 + 재주문 비활성화 (`be1bc5f`)
- **사후 보고 실체결 기반** — 부분체결 정직 보고 (`87a3dee`)

### ✅ `/status` 중복 출력 버그 해결 — webhook 멱등성 (`9f5a346`)
- **원인**: Telegram 은 webhook 응답이 느리면(Render free cold-start + `/status` 다중 KIS 호출 throttle) **같은 `update_id` 재전송** → 재전송분이 별도 요청으로 다시 처리되어 메시지 2개.
- **수정**: `update_id` 를 1회만 통과시키는 claim 게이트.
  - `migrations/002_processed_updates.sql` — `processed_updates(update_id PK)`.
  - `StateStore.claim_update(update_id)` — `INSERT ... ON CONFLICT DO NOTHING` + `rowcount` 원자 판정.
  - `TelegramBot.handle_update` — 인증·라우터 통과 후 claim, 중복이면 `False`(무시).
- 설계 메모: Render free 는 "200 먼저 응답 후 백그라운드 처리"가 spin-down 으로 작업 사망 위험 → **동기 처리 유지 + DB dedup** 선택. 다중턴 흐름은 각 턴이 별개 update_id 라 영향 없음.

### ✅ 후속 개선 3건 (`708002c`·`0ac80fe`·`9799af8`)
- `/status` 원화 병기: `kis_client.get_exrt()`(inquire-psamount `exrt`) + `StatusView.exrt` → `$100,000.00 (₩151,000,000)`. 환율 0/없으면 USD만(폴백).
- `/log` 체결가·잔고변화(표시 계층): `TradeRecord`에 `fill_price`·`balance_before`·`balance_after` + `read_trades` SELECT 확장.
- 거래일 게이트: `src/trading_calendar.py`(외부 의존성 0, `is_trading_day`, 미 증시 휴장일 2026~2030). `run_cycle` step 1.5 에서 비거래일이면 토큰 발급 전 스킵. ⚠️ `deps.now()`=서버 UTC 기준(cron UTC 15:30 = 미 동부 장중 → UTC date == ET 거래일). KST/tz-aware 로 바꾸면 하루 어긋나니 금지.

### ✅ 수익률 표시 — TWR/CAGR/평가손익률 + 입출금 기록 (`0d5e427`)
- 왜 TWR: 자금을 주기적으로 추가하는 운용이라 단순누적/CAGR은 입금 타이밍에 왜곡됨 → 시간가중수익률(TWR).
- `src/returns.py`(순수 함수): `compute_twr`(입출금 시점 `nav_before` 로 구간 분할)·`compute_cagr`(365일 미만 None)·`running_days`.
- `migrations/003_cash_flows.sql`: `cash_flows`(mode별) + 모의 시드 $100k(nav_before=0). `record_cash_flow`/`read_cash_flows`.
- `/deposit N`·`/withdraw N` — **`/help` 미노출 '숨은 명령'**. NAV 조회 → 확인(y/n) → 기록. **실전 전환 후 자금 추가 시에만** 사용. `web.py` 가 `nav_provider` 주입.
- `/status`: 보유 줄 평가손익률 병기 + `수익률(TWR)` + `CAGR`(1년 미만은 '운용 N개월' 안내).
- **라이브 검증 완료**: `evlu_pfls_rt` −0.82%, 마이그레이션 003 자동 적용, TWR −1.62% 정상 표시.
- **TWR tz 버그 수정** (`5573e8a`): Neon TIMESTAMPTZ → psycopg tz-aware / `datetime.now()` naive → `running_days` `TypeError`. `returns.py` `_naive_utc()` 헬퍼 + `web.py` `datetime.now(timezone.utc)`. 회귀 테스트 추가. 라이브 확인 완료.

### ✅ `/log` 체결가 저장 (`9eb356e`)
- `OrderResult.price`(주문 지정가) → `place_order` 가 담아 반환 → `record_trade` 가 `fill_price` 로 저장.
- 정기 월말 거래·`/emergency-stop` 둘 다 `transition.legs`(leg.order.price 포함)를 넘겨 저장.
- **한계(정직)**: 진짜 체결평균가(`Execution.avg_price`)가 아니라 **주문 지정가**(현재가 지정가의 근사). `get_executions` 스텁(0 반환) 해소 전까지 유지.
- ⚠️ **소급 안 됨** — 2026-06-16 2건은 가격 없이 저장 → `/log` 에 생략. 다음 거래부터 `@ $가격` 표시.

---

## Phase 마일스톤 (구현·테스트 완료)

### ✅ Phase A (워킹 스켈레톤) — PR #15
이슈 #1. 2서비스 Blueprint(`render.yaml`), Neon 스키마+자동 마이그레이션, 텔레그램 배선(`/help`·인증게이트·모드태그), `/healthcheck`, Cron 스텁.

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

## What Worked (회고)
- **인터페이스 격리**: httpx/psycopg를 엔트리포인트에서만 import → pytest가 외부 패키지 없이 실행.
- **오케스트레이션 분리**: `strategy_cycle.run_cycle(deps)` → mock 통합 테스트.
- **스택 브랜치**: Phase별 PR diff를 해당 Phase 파일로만 한정.
- **KIS 라이브 디버깅 방식**: 로그 → 트리거 → 원인 확정 → 수정 → push 사이클.
