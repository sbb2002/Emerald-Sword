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

## Phase B 후속/검증 필요 (handoff 참조)

- **KIS HTTP 어댑터(`kis_client.py`) 라이브 검증 필요**: 엔드포인트 경로·tr_id·응답 필드명은 KIS 문서 기준 확인 필요(모의투자 주문 1회 성공 확인). 로직 계층은 인터페이스 의존이라 어댑터 조정이 상위에 영향 없음.
- **ApprovalManager DB 백업 미구현**: web↔cron 프로세스 간 승인 영속이 필요(Phase C). 현재 인메모리 → `approvals` 테이블 백업 store로 교체.
- **대형 주문(>110%) 승인 게이트**: ApprovalManager(kind="large_order")는 있으나 주문 plan 산출과의 연결은 미구현.
- **DST/월 마지막 거래일 게이트**: render.yaml cron은 UTC 근사(28~31일). 거래일 캘린더 + DST 게이트 미구현(PRD 열린 질문 3).

## 비고

- Cron 스케줄(`30 15 28-31 * *`)은 Phase A 스텁용 근사. Phase B(#8)에서 월 마지막 거래일 + 미국 DST 게이트로 교체.
- 거래 종목 QQQM/GLDM 고정, 정수 주문, 기본 모드 `virtual` — CLAUDE.md 절대 규칙 준수.
