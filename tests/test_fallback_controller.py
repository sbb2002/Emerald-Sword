"""FallbackController — 폴백 분기 + 알림 (테스트 우선순위 #4)."""
from src.fallback_controller import (
    HOLIDAY,
    NO_ACTION,
    PROCEED,
    RETRY,
    SIX_HOURS,
    TWO_HOURS,
    FallbackController,
)


class FakeNotifier:
    def __init__(self):
        self.messages = []

    def __call__(self, text):
        self.messages.append(text)


def test_server_failure_retries_after_6h_and_notifies():
    n = FakeNotifier()
    d = FallbackController(n).on_server_failure()
    assert d.action == RETRY
    assert d.retry_after_seconds == SIX_HOURS
    assert len(n.messages) == 1


def test_market_closed_retries_within_limit():
    n = FakeNotifier()
    fc = FallbackController(n, max_market_retries=3)
    assert fc.on_market_closed(1).action == RETRY
    assert fc.on_market_closed(1).retry_after_seconds == TWO_HOURS
    assert fc.on_market_closed(3).action == RETRY  # 경계: 3회까지 재시도


def test_market_closed_becomes_holiday_after_limit():
    n = FakeNotifier()
    fc = FallbackController(n, max_market_retries=3)
    d = fc.on_market_closed(4)  # 한도 초과
    assert d.action == HOLIDAY


def test_insufficient_balance_no_action_and_notifies():
    n = FakeNotifier()
    d = FallbackController(n).check_balance(cash=100.0, needed=300.0)
    assert d.action == NO_ACTION
    assert len(n.messages) == 1


def test_sufficient_balance_proceeds_without_notify():
    n = FakeNotifier()
    d = FallbackController(n).check_balance(cash=1000.0, needed=300.0)
    assert d.action == PROCEED
    assert n.messages == []


def test_incomplete_fill_notifies_and_retries():
    n = FakeNotifier()
    d = FallbackController(n).on_incomplete_fill()
    assert d.action == RETRY
    assert len(n.messages) == 1
