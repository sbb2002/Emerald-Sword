"""테스트 공용 fixture — 외부 의존(DB·텔레그램·KIS)을 가짜로 대체한다.

CLAUDE.md 테스트 방침: 외부 행동(입력→출력/부수효과)만 검증하고 내부 구현 세부는 보지 않는다.
"""
from __future__ import annotations

import pytest

from src.commands import CommandDeps, CommandRouter, StatusView
from src.mode_manager import ModeManager
from src.momentum import SignalResult
from src.state_store import TradeRecord
from src.telegram_bot import TelegramBot


class FakeStore:
    """StateStore 의 인메모리 대역 (DB 없이 상태/거래로그만 흉내)."""

    def __init__(self, mode: str = "virtual", paused: bool = False, trades=None) -> None:
        self._mode = mode
        self._paused = paused
        self.trades = list(trades or [])  # 최신순 가정 (DB ORDER BY DESC 와 동일)

    def get_trading_mode(self) -> str:
        return self._mode

    def set_trading_mode(self, mode: str) -> None:
        self._mode = mode

    def is_paused(self) -> bool:
        return self._paused

    def set_paused(self, paused: bool) -> None:
        self._paused = paused

    def read_trades(self, limit=None):
        return self.trades[:limit] if limit else list(self.trades)

    def record_trade(self, *, mode, signal, legs, balance_before=None, balance_after=None,
                     reason="monthly_signal"):
        # StateStore.record_trade 와 동일하게 placed 인 leg 만 최신순으로 적재한다.
        for leg in legs:
            if not getattr(leg, "placed", False):
                continue
            self.trades.insert(0, TradeRecord(
                executed_at="now", mode=mode, signal=signal,
                side=leg.side, ticker=leg.symbol, quantity=leg.quantity, reason=reason,
            ))


class FakeSender:
    """TelegramSender 의 대역 — 실제 전송 대신 호출 내역을 기록한다."""

    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    def send_message(self, chat_id: int, text: str) -> None:
        self.sent.append((chat_id, text))


def fake_status() -> StatusView:
    return StatusView(holdings={"QQQM": 3}, cash=125.50, insufficient_for_next=False, server_ok=True)


def fake_signal() -> SignalResult:
    return SignalResult(target="NASDAQ", score_nasdaq=0.12, score_gold=0.05)


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


@pytest.fixture
def sender() -> FakeSender:
    return FakeSender()


@pytest.fixture
def deps(store: FakeStore) -> CommandDeps:
    return CommandDeps(store=store, status_provider=fake_status, signal_provider=fake_signal)


@pytest.fixture
def router(deps: CommandDeps) -> CommandRouter:
    return CommandRouter(deps)


@pytest.fixture
def bot(store: FakeStore, sender: FakeSender, router: CommandRouter) -> TelegramBot:
    return TelegramBot(
        allowed_chat_id=42,
        mode_manager=ModeManager(store),
        sender=sender,
        store=store,
        router=router,
    )
