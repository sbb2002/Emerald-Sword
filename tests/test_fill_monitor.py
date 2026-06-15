"""PartialFillHandler — 부분 체결 감지 + 재시도."""
from src.fill_monitor import PartialFillHandler
from src.kis_interface import Execution, OrderResult
from src.order_executor import Leg, TransitionResult


class FakeClient:
    def __init__(self, initial_fills, fill_on_retry=True):
        self.fills = dict(initial_fills)  # order_id -> filled qty
        self.fill_on_retry = fill_on_retry
        self.placed = []
        self._n = 0

    def get_executions(self, order_id):
        return Execution(order_id=order_id, symbol="", side="", filled_qty=self.fills.get(order_id, 0), avg_price=0.0)

    def place_order(self, symbol, side, quantity):
        self._n += 1
        oid = f"retry{self._n}"
        self.placed.append((symbol, side, quantity))
        self.fills[oid] = quantity if self.fill_on_retry else 0
        return OrderResult(order_id=oid, symbol=symbol, side=side, quantity=quantity, accepted=True)


def _transition():
    sell = Leg("SELL", "GLDM", 4, placed=True, order=OrderResult("o1", "GLDM", "SELL", 4, True))
    buy = Leg("BUY", "QQQM", 3, placed=True, order=OrderResult("o2", "QQQM", "BUY", 3, True))
    return TransitionResult(target="NASDAQ", target_symbol="QQQM", legs=[sell, buy], complete=False)


def test_full_fill_no_retry():
    client = FakeClient({"o1": 4, "o2": 3})
    report = PartialFillHandler(client).settle(_transition())
    assert report.complete is True
    assert report.retries_used == 0
    assert client.placed == []  # 재주문 없음


def test_partial_leg_retried_until_complete():
    # 매수 leg 미체결(o2=0) → 잔여 3주 재주문, 재주문은 완전 체결
    client = FakeClient({"o1": 4, "o2": 0}, fill_on_retry=True)
    report = PartialFillHandler(client, max_retries=3).settle(_transition())
    assert report.complete is True
    assert report.retries_used == 1
    assert ("QQQM", "BUY", 3) in client.placed


def test_stays_incomplete_after_max_retries():
    # 재주문해도 계속 미체결 → 최대 재시도 후 미완료로 보고
    client = FakeClient({"o1": 4, "o2": 0}, fill_on_retry=False)
    report = PartialFillHandler(client, max_retries=3).settle(_transition())
    assert report.complete is False
    assert report.retries_used == 3
    incomplete = report.incomplete
    assert len(incomplete) == 1
    assert incomplete[0].symbol == "QQQM"
