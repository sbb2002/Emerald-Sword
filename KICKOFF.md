# KICKOFF — 복합모멘텀 QQQM/GLDM 봇

프로젝트 기획·명세는 [`blueprints/PRD_momentum_bot.md`](blueprints/PRD_momentum_bot.md)가 단일 진실 원천이다.
이 문서는 구현 중 내린 **의사결정 로그**를 누적한다.

## 의사결정 로그

| 날짜 | 이슈 | 결정 | 이유 | 포기한 대안 |
|---|---|---|---|---|
| 2026-06-15 | #1 (Phase A) | 웹 프레임워크 = FastAPI + uvicorn | 비동기, Pydantic webhook 검증, /healthcheck 간결, 테스트 용이 | Flask + gunicorn |
| 2026-06-15 | #1 (Phase A) | DB 접근 = psycopg3 + 원시 SQL 마이그레이션 | PRD "마이그레이션 파일로 관리" 방침 부합, 경량, mock 용이 | SQLAlchemy + Alembic (5개 테이블엔 과함) |
| 2026-06-15 | #1 (Phase A) | 마이그레이션 자동 실행 = web startup(lifespan) + cron 시작 시 `run_migrations()` | Render free tier preDeployCommand 의존 제거, 멱등 보장 | preDeployCommand 단독 |
| 2026-06-15 | #1 (Phase A) | webhook 경로 = `/webhook/{token}` (봇 토큰을 경로 비밀로) | 새 env 추가 없이 비인가 POST 차단 + chat_id 게이트가 본 인증 | 별도 `TELEGRAM_WEBHOOK_SECRET` env |
| 2026-06-15 | #1 (Phase A) | 모드 태그 단일 주입점 = `ModeManager.decorate()`, 발신은 `TelegramBot.send_message()` 경유 | "모든 발신 머리에 [모의]/[실전]" 규칙을 한 곳에서 강제 | 각 호출부에서 태그 부착 |
| 2026-06-15 | #1 (Phase A) | 중복 이슈 #1/#2 → #1 정본, #2 닫음 | 동일 내용 중복 제거 | 둘 다 유지 |
| 2026-06-16 | #3 | MomentumEngine 순수함수, 동률 시 NASDAQ 우선 | 결정론적 타이브레이크(실데이터 정확 동률 사실상 없음) | 현 보유 유지식 타이브레이크 |
| 2026-06-16 | #3 | 회귀 데이터 = 합성 픽스처 + historical_data.csv 자동감지(없으면 skip) | 실 CSV 부재, 항상 통과하는 회귀 확보 | 실 CSV 직접 제공 |
| 2026-06-16 | #4 | KIS 인터페이스(kis_interface)를 httpx 비의존으로 분리 | 로직/테스트를 무거운 의존성 없이 실행 | 로직이 httpx 클라이언트 직접 의존 |
| 2026-06-16 | #4 | TokenManager 사이클당 1회 발급·만료(마진) 시에만 재발급 | KIS 분당 1회 발급 제한 회피 | 호출마다 발급 |
| 2026-06-16 | #5 | 월말 종가 = 각 달 마지막 거래일 종가 | 말일 결측 시 직전 거래일 자동 선택(폴백 효과) | 명시적 말일 탐색 루프 |
| 2026-06-16 | #6 | 멱등성 = 목표 보유 시 매수 스킵 + 미체결 동일주문 재주문 스킵 | 재실행·동일 신호 churn 및 이중 주문 방지 | 매번 무조건 주문 |
| 2026-06-16 | #9 | ApprovalManager 영속화를 ApprovalStore 인터페이스로 분리(인메모리 테스트) | 상태기계 로직만 격리 테스트 | DB 직접 결합 |
| 2026-06-16 | #8 | 오케스트레이션을 strategy_cycle로 분리, cron은 배선만 | mock 통합 테스트 가능 | cron에 로직 직접 작성 |
| 2026-06-16 | #3–#10 | phase-b 브랜치를 phase-a/skeleton 위에 스택, PR base=phase-a | 미머지 Phase A 의존 + 깔끔한 diff | main 분기(인프라 파일 누락) |
| 2026-06-16 | #11–#14 | 무상태 `dispatch()` → 상태머신 `CommandRouter`(의존성 주입) | 다중턴 확인(y/n)·챌린지·60초 타임아웃이 명령 상태를 요구 | 명령마다 별도 무상태 핸들러 |
| 2026-06-16 | #11–#14 | 펜딩 대화상태 = chat_id별 1건 **인메모리**(DB 비영속) | 수 초 수명·web 단일 프로세스·단일 사용자. 유실돼도 재입력으로 무해(액션은 확인 후에만 실행) | DB 영속(과설계) |
| 2026-06-16 | #11–#14 | 펜딩 중 새 `/명령` 도착 시 펜딩 폐기 후 새 명령 처리 | 명령 유실 방지 + 챌린지를 명령으로 오인한 오발 방지 | 펜딩이 모든 다음 입력을 흡수 |
| 2026-06-16 | #11/#13/#14 | 조회·청산용 KIS 클라이언트를 **요청 시점**에 현재 `trading_mode`로 빌드 | 런타임 `/virtual`·`/real` 전환 후에도 올바른 계좌/URL. 저빈도라 호출당 토큰 발급 무관 | startup 시 1회 빌드(모드 전환 시 stale) |
| 2026-06-16 | #11 | `db.py`의 `psycopg` import를 지연(함수 내부)으로 이동 | `state_store.TradeRecord`를 psycopg 없이 import → 테스트 격리 유지 | top-level import(테스트가 psycopg 요구) |
| 2026-06-16 | #12 | `/pause`의 "진행 중 거래 취소"는 `is_paused` 게이트(사이클 스킵)로 실현 | KIS에 주문취소 API 없음. cron이 기상 시 is_paused=True면 로직 전체 스킵 | 미체결 취소 API 호출(부재) |
| 2026-06-16 | #14 | `/emergency-stop` 청산을 **Web Service에서 즉시 실행**(결정 B) | User Story 31 "즉시 위험 제거" — 월 1회 cron으론 즉시성 불가. 사용자가 명령하는 유일한 즉시 매매 | DB 플래그만 세팅 후 cron 대기(즉시성 상실) |
| 2026-06-16 | #14 | **early-pause**: 청산 주문 *전에* `set_paused(True)` | 청산 도중 크래시해도 '정지+일부청산' 안전 실패 모드 → 재매수 차단 유지. execute("CASH") 멱등이라 재실행 마무리 | 청산 후 pause(크래시 시 재매수 위험) |
| 2026-06-16 | #14 | 60초 타임아웃 = **수동 만료**(만료 후 정확한 코드도 거부) | 백그라운드 타이머 불필요·테스트 결정적(clock 주입). 무응답 시 액션 미발생=자동취소 | 백그라운드 스레드 타이머 |

## Phase B 후속/검증 필요 (handoff 참조)

- **KIS HTTP 어댑터(`kis_client.py`) 라이브 검증 필요**: 엔드포인트 경로·tr_id·응답 필드명은 KIS 문서 기준 확인 필요(모의투자 주문 1회 성공 확인). 로직 계층은 인터페이스 의존이라 어댑터 조정이 상위에 영향 없음.
- **ApprovalManager DB 백업 미구현**: web↔cron 프로세스 간 승인 영속이 필요(Phase C). 현재 인메모리 → `approvals` 테이블 백업 store로 교체.
- **대형 주문(>110%) 승인 게이트**: ApprovalManager(kind="large_order")는 있으나 주문 plan 산출과의 연결은 미구현.
- **DST/월 마지막 거래일 게이트**: render.yaml cron은 UTC 근사(28~31일). 거래일 캘린더 + DST 게이트 미구현(PRD 열린 질문 3).

## 비고

- Cron 스케줄(`30 15 28-31 * *`)은 Phase A 스텁용 근사. Phase B(#8)에서 월 마지막 거래일 + 미국 DST 게이트로 교체.
- 거래 종목 QQQM/GLDM 고정, 정수 주문, 기본 모드 `virtual` — CLAUDE.md 절대 규칙 준수.
