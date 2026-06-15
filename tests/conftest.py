"""테스트 공용 fixture — 외부 의존(DB·텔레그램)을 가짜로 대체한다.

CLAUDE.md 테스트 방침: 외부 행동(입력→출력/부수효과)만 검증하고 내부 구현 세부는 보지 않는다.
"""
from __future__ import annotations

import pytest

from src.mode_manager import ModeManager
from src.telegram_bot import TelegramBot


class FakeStore:
    """StateStore 의 인메모리 대역 (DB 없이 모드/일시정지 상태만 흉내)."""

    def __init__(self, mode: str = "virtual", paused: bool = False) -> None:
        self._mode = mode
        self._paused = paused

    def get_trading_mode(self) -> str:
        return self._mode

    def set_trading_mode(self, mode: str) -> None:
        self._mode = mode

    def is_paused(self) -> bool:
        return self._paused

    def set_paused(self, paused: bool) -> None:
        self._paused = paused


class FakeSender:
    """TelegramSender 의 대역 — 실제 전송 대신 호출 내역을 기록한다."""

    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    def send_message(self, chat_id: int, text: str) -> None:
        self.sent.append((chat_id, text))


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


@pytest.fixture
def sender() -> FakeSender:
    return FakeSender()


@pytest.fixture
def bot(store: FakeStore, sender: FakeSender) -> TelegramBot:
    return TelegramBot(
        allowed_chat_id=42,
        mode_manager=ModeManager(store),
        sender=sender,
        store=store,
    )
