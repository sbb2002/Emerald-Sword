"""Web Service — 텔레그램 webhook 수신 + /healthcheck (FastAPI).

- 시작 시(lifespan) DB 마이그레이션을 자동 실행한다.
- POST /webhook/{token}: 봇 토큰 경로 검증 → chat_id 인증 게이트(TelegramBot 내부) → 명령 처리.
- GET /healthcheck: UptimeRobot keep-alive 대상, 200 반환.
이 서비스는 매매하지 않는다(상태 변경·조회·알림 응답만 — PRD 아키텍처).
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.concurrency import run_in_threadpool

from .config import get_settings
from .migrate import run_migrations
from .mode_manager import ModeManager
from .state_store import StateStore
from .telegram_bot import TelegramBot
from .telegram_client import TelegramClient


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    run_migrations(settings.database_url)  # 자동 마이그레이션
    store = StateStore(settings.database_url)
    mode = ModeManager(store)
    sender = TelegramClient(settings.telegram_bot_token)
    app.state.settings = settings
    app.state.bot = TelegramBot(settings.telegram_chat_id, mode, sender, store=store)
    yield


app = FastAPI(title="Emerald-Sword Web", lifespan=lifespan)


@app.get("/healthcheck")
async def healthcheck() -> dict:
    return {"status": "ok"}


@app.get("/")
async def root() -> dict:
    return {"service": "emerald-sword-web", "status": "ok"}


@app.post("/webhook/{token}")
async def telegram_webhook(token: str, request: Request) -> Response:
    settings = request.app.state.settings
    # 봇 토큰을 아는 발신자만 허용(경로 비밀). 본 인증은 그 다음의 chat_id 게이트.
    if token != settings.telegram_bot_token:
        return Response(status_code=403)
    try:
        update: dict[str, Any] = await request.json()
    except Exception:
        return Response(status_code=200)  # 잘못된 본문 — 텔레그램 재시도 막기 위해 200
    await run_in_threadpool(request.app.state.bot.handle_update, update)
    return Response(status_code=200)  # 텔레그램에는 항상 200
