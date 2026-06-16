"""Web Service — 텔레그램 webhook 수신 + /healthcheck (FastAPI).

- 시작 시(lifespan) DB 마이그레이션을 자동 실행한다.
- POST /webhook/{token}: 봇 토큰 경로 검증 → chat_id 인증 게이트(TelegramBot 내부) → 명령 처리.
- GET /healthcheck: 헬스체크용 200 반환 (keep-alive 미사용 — 유휴 시 spin-down 허용).
이 서비스는 매매하지 않는다(상태 변경·조회·알림 응답만 — PRD 아키텍처. 단 /emergency-stop 청산만 예외).
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.concurrency import run_in_threadpool

from .commands import CommandDeps, CommandRouter, StatusView
from .config import get_settings
from .kis_client import build_kis_client
from .logging_setup import setup_logging
from .market_data import MarketDataProvider
from .migrate import run_migrations
from .mode_manager import ModeManager
from .momentum import decide_signal
from .order_executor import OrderExecutor
from .position_service import PositionService
from .state_store import StateStore
from .telegram_bot import TelegramBot
from .telegram_client import TelegramClient

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    settings = get_settings()
    run_migrations(settings.database_url)  # 자동 마이그레이션
    store = StateStore(settings.database_url)
    mode = ModeManager(store)
    sender = TelegramClient(settings.telegram_bot_token)

    # 조회 명령(#11)용 provider — 호출 시점의 trading_mode 로 KIS 엔드포인트를 구성한다
    # (런타임 /virtual·/real 전환 후에도 올바른 계좌/URL 로 조회되도록 요청마다 빌드).
    def _kis():
        return build_kis_client(settings, store.get_trading_mode())

    def status_provider() -> StatusView:
        try:
            kis = _kis()
            snap = PositionService(kis).snapshot()
            prices = []
            for sym in ("QQQM", "GLDM"):
                try:
                    px = kis.get_price(sym)
                    if px > 0:
                        prices.append(px)
                except Exception:
                    pass
            cheapest = min(prices) if prices else 0.0
            insufficient = bool(cheapest > 0 and snap.cash < cheapest)
            return StatusView(
                holdings=snap.holdings, cash=snap.cash,
                insufficient_for_next=insufficient, server_ok=True,
            )
        except Exception:
            # KIS 도달 실패 등 — 서버 상태를 '오류'로 표시(명령 자체는 200 으로 응답).
            return StatusView(holdings={}, cash=0.0, insufficient_for_next=True, server_ok=False)

    def signal_provider():
        kis = _kis()
        md = MarketDataProvider(kis)
        nasdaq = md.get("QQQM", 13)
        gold = md.get("GLDM", 13)
        return decide_signal(nasdaq.month_end_closes, gold.month_end_closes)

    def liquidator():
        # /emergency-stop 전량 청산 — 사용자가 명령한 유일한 즉시 매매(현재 모드 계좌로).
        kis = _kis()
        pos = PositionService(kis)
        return OrderExecutor(kis, pos, mode=store.get_trading_mode()).execute("CASH")

    router = CommandRouter(
        CommandDeps(
            store=store,
            status_provider=status_provider,
            signal_provider=signal_provider,
            liquidator=liquidator,
        )
    )
    app.state.settings = settings
    app.state.bot = TelegramBot(settings.telegram_chat_id, mode, sender, store=store, router=router)
    base = os.environ.get("RENDER_EXTERNAL_URL", "https://<your-host>")
    logger.info(
        "web 시작 완료 — allowed_chat_id=%s, trading_mode=%s. "
        "텔레그램 webhook 을 이 URL 로 등록하세요: %s/webhook/<BOT_TOKEN>",
        settings.telegram_chat_id, store.get_trading_mode(), base,
    )
    yield


app = FastAPI(title="Emerald-Sword Web", lifespan=lifespan)


@app.get("/healthcheck")
async def healthcheck() -> dict:
    return {"status": "ok"}


@app.get("/")
async def root() -> dict:
    return {"service": "emerald-sword-web", "status": "ok"}


@app.post("/")
async def misrouted_webhook() -> Response:
    # 텔레그램이 루트(/)로 POST → setWebhook URL 이 호스트만 등록되고 /webhook/<BOT_TOKEN> 경로가 빠진 경우.
    logger.warning(
        "⚠️ POST / 수신 — 텔레그램 webhook 이 루트(/)로 등록된 것으로 보입니다. "
        "setWebhook 을 https://<host>/webhook/<BOT_TOKEN> 로 재등록하세요. "
        "(이 업데이트는 처리되지 않고 무시됩니다)"
    )
    return Response(status_code=200)  # 405 대신 200 — 텔레그램 재시도 폭주 방지


@app.post("/webhook/{token}")
async def telegram_webhook(token: str, request: Request) -> Response:
    settings = request.app.state.settings
    # 봇 토큰을 아는 발신자만 허용(경로 비밀). 본 인증은 그 다음의 chat_id 게이트.
    if token != settings.telegram_bot_token:
        logger.warning("webhook 토큰 불일치 — 403 거부 (잘못된 URL/토큰으로 POST 수신)")
        return Response(status_code=403)
    try:
        update: dict[str, Any] = await request.json()
    except Exception:
        logger.warning("webhook 본문 JSON 파싱 실패 — 200 반환")
        return Response(status_code=200)  # 잘못된 본문 — 텔레그램 재시도 막기 위해 200
    logger.info("webhook 수신: update_id=%s", update.get("update_id"))
    try:
        await run_in_threadpool(request.app.state.bot.handle_update, update)
    except Exception:
        # 명령 처리/발신 실패가 텔레그램 재시도 폭주로 번지지 않도록 항상 200(상세는 서버 로그).
        logger.exception("handle_update 처리 중 예외 — 200 반환")
    return Response(status_code=200)  # 텔레그램에는 항상 200
