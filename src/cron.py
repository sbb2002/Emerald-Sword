"""Cron Job — 월말 전략 사이클 진입점 (Phase B).

실제 의존성(KIS·텔레그램·DB)을 구성해 strategy_cycle.run_cycle 에 주입한다.
오케스트레이션 로직 자체는 strategy_cycle 에 있고 mock 으로 통합 테스트된다(이 파일은 배선만).

is_paused 게이트·신호 산출·2-leg 전환·체결 정산·사후 보고는 run_cycle 이 수행한다.
"""
from __future__ import annotations

import logging

from .approval_manager import ApprovalManager, InMemoryApprovalStore
from .config import get_settings
from .fallback_controller import FallbackController
from .fill_monitor import PartialFillHandler
from .kis_client import build_kis_client
from .logging_setup import setup_logging
from .market_data import MarketDataProvider
from .migrate import run_migrations
from .mode_manager import ModeManager
from .order_executor import OrderExecutor
from .position_service import PositionService
from .state_store import StateStore
from .strategy_cycle import CycleDeps, run_cycle
from .telegram_bot import TelegramBot
from .telegram_client import TelegramClient
from .token_manager import TokenManager

logger = logging.getLogger(__name__)


def main() -> None:
    setup_logging()
    settings = get_settings()
    run_migrations(settings.database_url)  # 스키마 보장

    store = StateStore(settings.database_url)
    mode = store.get_trading_mode()  # 실전/모의 분기 (기본 virtual)

    mode_manager = ModeManager(store)
    sender = TelegramClient(settings.telegram_bot_token)
    bot = TelegramBot(settings.telegram_chat_id, mode_manager, sender, store=store)

    kis = build_kis_client(settings, mode)  # 모드에 맞는 BASE URL·계좌
    token_manager = TokenManager(kis.issue_token)
    positions = PositionService(kis)
    executor = OrderExecutor(kis, positions, mode=mode)
    fill_handler = PartialFillHandler(kis)
    fallback = FallbackController(bot.send_message)
    market = MarketDataProvider(kis)
    # NOTE: 승인은 web↔cron 프로세스 간 영속이 필요(Phase C). 지금은 인메모리 — DB백업 ApprovalStore로 교체 예정.
    approvals = ApprovalManager(InMemoryApprovalStore())

    deps = CycleDeps(
        store=store,
        notify=bot.send_message,
        token_manager=token_manager,
        market_data=market,
        positions=positions,
        order_executor=executor,
        fill_handler=fill_handler,
        fallback=fallback,
        approvals=approvals,
        mode=mode,
    )

    logger.info("cron 사이클 시작: trading_mode=%s", mode)
    result = run_cycle(deps)
    logger.info("cron 사이클 종료: status=%s target=%s", result.status, result.target)


if __name__ == "__main__":
    main()
