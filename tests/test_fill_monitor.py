"""PartialFillHandler — 접수 정산 + 중복 주문 방지.

핵심 회귀: get_executions 가 스텁(0)인 동안 settle 이 '재주문'을 하면 접수된 주문을
미체결로 오판해 중복 매수가 난다. 따라서 settle 은 어떤 경우에도 재주문하지 않는다.
"""
from src.fill_monitor import PartialFillHandler
from src.kis_interface import OrderResult
from src.order_executor import Leg, TransitionResult


class FakeClient:
    """place_order 호출을 기록 — settle 이 재주문하지 않는지 검증."""

    def __init__(self):
        self.placed = []

    def place_order(self, symbol, side, quantity):
        self.placed.append((symbol, side, quantity))
        return OrderResult(order_id="x", symbol=symbol, side=side, quantity=quantity, accepted=True)


def _transition(sell_accepted=True, buy_accepted=True):
    sell = Leg("SELL", "GLDM", 4, placed=True,
               order=OrderResult("o1", "GLDM", "SELL", 4, sell_accepted))
    buy = Leg("BUY", "QQQM", 3, placed=True,
              order=OrderResult("o2", "QQQM", "BUY", 3, buy_accepted))
    return TransitionResult(target="NASDAQ", target_symbol="QQQM", legs=[sell, buy], complete=False)


def test_all_accepted_complete_without_reorder():
    # 접수된 2개 leg → 완료로 정산하고 '재주문하지 않는다'(중복 매수 방지).
    client = FakeClient()
    report = PartialFillHandler(client).settle(_transition())
    assert report.complete is True
    assert report.retries_used == 0
    assert client.placed == []


def test_rejected_leg_is_incomplete_without_reorder():
    # 매수 leg 거부(accepted=False) → 미완료로 보고하되, 재주문은 하지 않는다.
    client = FakeClient()
    report = PartialFillHandler(client).settle(_transition(buy_accepted=False))
    assert report.complete is False
    incomplete = report.incomplete
    assert len(incomplete) == 1
    assert incomplete[0].symbol == "QQQM"
    assert client.placed == []


def test_skipped_legs_are_ignored():
    # placed=False(멱등 스킵 등)인 leg 는 정산 대상이 아니다.
    sell = Leg("SELL", "GLDM", 4, placed=True, order=OrderResult("o1", "GLDM", "SELL", 4, True))
    skip = Leg("BUY", "QQQM", 0, placed=False, skipped_reason="already_holding_target")
    transition = TransitionResult(target="NASDAQ", target_symbol="QQQM", legs=[sell, skip], complete=False)
    report = PartialFillHandler(FakeClient()).settle(transition)
    assert report.complete is True
    assert len(report.legs) == 1
