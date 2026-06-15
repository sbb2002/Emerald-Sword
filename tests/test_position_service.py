"""PositionService — 실시간 조회, 내부 캐시 없음."""
from src.position_service import PositionService


class FakeKis:
    def __init__(self, holdings: dict, cash: float) -> None:
        self._holdings = holdings
        self._cash = cash
        self.holdings_calls = 0
        self.cash_calls = 0

    def get_holdings(self) -> dict:
        self.holdings_calls += 1
        return dict(self._holdings)

    def get_cash(self) -> float:
        self.cash_calls += 1
        return self._cash


def test_snapshot_returns_holdings_and_cash():
    svc = PositionService(FakeKis({"QQQM": 3}, 1234.5))
    snap = svc.snapshot()
    assert snap.holdings == {"QQQM": 3}
    assert snap.cash == 1234.5


def test_no_internal_cache_queries_each_call():
    kis = FakeKis({"QQQM": 3}, 100.0)
    svc = PositionService(kis)
    svc.snapshot()
    svc.snapshot()
    assert kis.holdings_calls == 2
    assert kis.cash_calls == 2


def test_held_quantity_defaults_zero():
    svc = PositionService(FakeKis({"GLDM": 5}, 0.0))
    assert svc.held_quantity("GLDM") == 5
    assert svc.held_quantity("QQQM") == 0
