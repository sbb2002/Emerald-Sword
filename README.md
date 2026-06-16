# Emerald-Sword

나스닥100(**QQQM**)과 금(**GLDM**)의 3·6·12개월 모멘텀 평균을 매월 말 비교해 더 강한 자산으로
100% 전환하는 반자동 자동매매 봇. 둘 다 모멘텀이 음수면 현금 보유.

- 구현 명세 단일 진실 원천: [`blueprints/PRD_momentum_bot.md`](blueprints/PRD_momentum_bot.md)
- 사용자 사전 준비(계정·키 발급): [`blueprints/SETUP_사용자_준비절차.md`](blueprints/SETUP_사용자_준비절차.md)
- 배포·검증·운영 매뉴얼(현재 구현 기준): [`docs/USER_MANUAL.md`](docs/USER_MANUAL.md)

## 아키텍처

두 Render 서비스가 **직접 통신하지 않고 Neon PostgreSQL만 공유**한다.

| 컴포넌트 | 역할 | 실행 주기 | 진입점 |
|---|---|---|---|
| Web Service | 텔레그램 webhook 수신 → 명령 처리 → DB 갱신 (매매 안 함) | 상시 (UptimeRobot 5분 핑) | `src/web.py` (`uvicorn src.web:app`) |
| Cron Job | `is_paused` 확인 → 모멘텀 계산 → 주문 | 매월 말 자정(KST) | `src/cron.py` (`python -m src.cron`) |

## 진행 상황

- **Phase A (워킹 스켈레톤)** — 2서비스 배포 골격, DB 마이그레이션, 텔레그램 배선(`/help`·`/healthcheck`), Cron 스텁. ✅
- **Phase B** — MomentumEngine, KIS 연동, OrderExecutor, 폴백·승인, cron 전략 사이클 (이슈 #3–#10). ✅
- **Phase C** — 텔레그램 명령(`/status`·`/signal`·`/log`·`/pause`·`/resume`·`/virtual`·`/real`·`/emergency-stop`), 모드 전환·챌린지 (이슈 #11–#14). ✅
- 테스트: `python -m pytest` → 81 passed, 1 skipped. **실운영 전 KIS 어댑터 라이브 검증 필요** → [`docs/USER_MANUAL.md`](docs/USER_MANUAL.md) §4.

## 로컬 실행

```bash
# 1) 의존성
pip install -r requirements-dev.txt

# 2) 환경변수 (.env.example 복사 후 값 채우기 — .env 는 커밋 금지)
cp .env.example .env

# 3) 테스트 (외부 의존 없이 봇 로직 검증)
pytest

# 4) DB 마이그레이션 (DATABASE_URL 필요)
python -m src.migrate

# 5) Web 로컬 구동
uvicorn src.web:app --reload --port 8000
#   GET  http://localhost:8000/healthcheck   → {"status":"ok"}

# 6) Cron 1회 실행 (DB의 is_paused 읽고 텔레그램 보고)
python -m src.cron
```

## 텔레그램 webhook 등록

web service 공개 URL이 생기면 1회 등록한다(봇 토큰을 경로 비밀로 사용):

```
https://api.telegram.org/bot<BOT_TOKEN>/setWebhook?url=https://<your-host>/webhook/<BOT_TOKEN>
```

등록 후 봇에게 `/help` 를 보내면 명령어 목록이 `[모의]`/`[실전]` 태그와 함께 돌아온다.

## 배포

`render.yaml` Blueprint로 web + cron 두 서비스를 한 번에 생성한다. 비밀값은 `emerald-sword-secrets`
env 그룹에 입력한다. `/healthcheck` 를 UptimeRobot 5분 핑 대상으로 등록해 spin-down을 방지한다.

## 보안 규칙

비밀값(KIS 키·텔레그램 토큰·DB URL)은 코드·git에 절대 두지 않는다. 전부 Render 환경변수.
거래 종목은 QQQM/GLDM 고정, 정수 주문만, 기본 모드는 `virtual`.
