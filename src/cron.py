"""Cron Job — 월말 사이클 진입점 (Phase A 스텁).

기상 즉시 DB의 is_paused 를 읽어:
  - True  → "일시정지 중" 알림만 보내고 종료
  - False → "사이클 시작" 알림 (Phase B에서 모멘텀 계산·주문으로 확장)
이 스텁은 아직 매매하지 않는다.
"""
from __future__ import annotations

from .config import get_settings
from .migrate import run_migrations
from .mode_manager import ModeManager
from .state_store import StateStore
from .telegram_bot import TelegramBot
from .telegram_client import TelegramClient


def main() -> None:
    settings = get_settings()
    run_migrations(settings.database_url)  # web가 한 번도 안 떴어도 스키마 보장

    store = StateStore(settings.database_url)
    mode = ModeManager(store)
    sender = TelegramClient(settings.telegram_bot_token)
    bot = TelegramBot(settings.telegram_chat_id, mode, sender, store=store)

    if store.is_paused():
        bot.send_message("⏸️ 자동거래 일시정지 중 — 이번 월말 사이클을 건너뜁니다.")
    else:
        bot.send_message(
            "▶️ 월말 사이클 시작 — 전략 실행 준비 완료.\n"
            "(Phase A 스텁: 모멘텀 계산·주문은 Phase B에서 동작합니다.)"
        )


if __name__ == "__main__":
    main()
