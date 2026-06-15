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

## 비고

- Cron 스케줄(`30 15 28-31 * *`)은 Phase A 스텁용 근사. Phase B(#8)에서 월 마지막 거래일 + 미국 DST 게이트로 교체.
- 거래 종목 QQQM/GLDM 고정, 정수 주문, 기본 모드 `virtual` — CLAUDE.md 절대 규칙 준수.
