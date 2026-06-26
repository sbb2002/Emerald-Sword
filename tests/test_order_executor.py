"""OrderExecutor — 2-leg 전환 + 멱등성 + 정수 주문 (테스트 우선순위 #2)."""
from unittest.mock import patch

from src.kis_interface import OrderResult
from src.order_executor import OrderExecutor, _SETTLE_INTERVAL
from src.position_service import PositionService


class FakeKis:
    def __init__(self, holdings, cash, price, open_orders=None, sll_ruse_seq=None):
        self._holdings = holdings
        self._cash = cash
        self._price = price
        self._open = open_orders or []
        self.orders = []  # 실제 낸 주문 (symbol, side, qty)
        # sll_ruse_seq: get_sll_ruse_amt 호출마다 꺼낼 값 목록. 기본값 [0.0] (즉시 정산).
        self._sll_ruse_seq = list(sll_ruse_seq or [0.0])
        self.sll_ruse_calls = 0  # 호출 횟수 검증용

    def get_holdings(self):
        return dict(self._holdings)

    def get_cash(self):
        return self._cash

    def get_price(self, symbol):
        return self._price

    def get_buyable_qty(self, symbol, price):
        # 실제 KIS 는 max_ord_psbl_qty 를 주지만, 테스트에선 floor(cash/price) 로 동일 검증.
        return int(self._cash // price) if price > 0 else 0

    def get_sll_ruse_amt(self, symbol, price):
        self.sll_ruse_calls += 1
        if self._sll_ruse_seq:
            return self._sll_ruse_seq.pop(0)
        return 0.0

    def get_open_orders(self):
        return list(self._open)

    def place_order(self, symbol, side, quantity):
        self.orders.append((symbol, side, quantity))
        # 실제 place_order 처럼 현재가를 지정가(price)로 담는다 — 거래 로그 fill_price 출처.
        return OrderResult(order_id=f"o{len(self.orders)}", symbol=symbol, side=side,
                           quantity=quantity, accepted=True, price=self._price)


def _exec(kis):
    return OrderExecutor(kis, PositionService(kis))


def test_enter_from_cash_buys_integer_qty():
    kis = FakeKis(holdings={}, cash=1000.0, price=300.0)
    res = _exec(kis).execute("NASDAQ")
    assert kis.orders == [("QQQM", "BUY", 3)]  # floor(1000/300)=3
    assert res.complete is True


def test_buy_quantity_is_floored():
    kis = FakeKis(holdings={}, cash=1000.0, price=291.0)  # 3.43 → 3
    _exec(kis).execute("NASDAQ")
    assert kis.orders == [("QQQM", "BUY", 3)]


def test_switch_sells_then_buys():
    kis = FakeKis(holdings={"GLDM": 4}, cash=1000.0, price=300.0)
    res = _exec(kis).execute("NASDAQ")
    assert ("GLDM", "SELL", 4) in kis.orders
    assert ("QQQM", "BUY", 3) in kis.orders
    assert len(kis.orders) == 2


def test_idempotent_when_already_in_target():
    # 이미 목표 종목 보유 → 재실행해도 주문 없음 (멱등)
    kis = FakeKis(holdings={"QQQM": 5}, cash=0.0, price=300.0)
    res = _exec(kis).execute("NASDAQ")
    assert kis.orders == []
    assert res.complete is True


def test_skips_when_open_order_pending():
    pending = [OrderResult(order_id="x", symbol="GLDM", side="SELL", quantity=4, accepted=True)]
    kis = FakeKis(holdings={"GLDM": 4}, cash=0.0, price=300.0, open_orders=pending)
    res = _exec(kis).execute("NASDAQ")
    assert kis.orders == []  # 미체결 매도 대기 → 재주문 없음, 현금 부족으로 매수 보류


def test_cash_target_sells_all_holdings():
    kis = FakeKis(holdings={"QQQM": 5}, cash=0.0, price=300.0)
    res = _exec(kis).execute("CASH")
    assert kis.orders == [("QQQM", "SELL", 5)]
    assert res.target_symbol is None


def test_insufficient_cash_no_buy():
    kis = FakeKis(holdings={}, cash=100.0, price=300.0)  # 1주 미만
    res = _exec(kis).execute("NASDAQ")
    assert kis.orders == []


def test_placed_leg_carries_order_price():
    # 주문 지정가가 leg.order.price 로 보존돼야 거래 로그(fill_price)·/log 에 남는다.
    kis = FakeKis(holdings={"GLDM": 4}, cash=1000.0, price=300.0)
    res = _exec(kis).execute("NASDAQ")
    placed = {leg.symbol: leg for leg in res.legs if leg.placed}
    assert placed["GLDM"].order.price == 300.0   # 매도 leg 도 지정가 보존
    assert placed["QQQM"].order.price == 300.0   # 매수 leg


# ── 정산 대기 폴링 ──────────────────────────────────────────────────────────────

def test_settlement_wait_called_after_sell(monkeypatch):
    # 매도 후 sll_ruse_amt 가 0 이 되면 즉시 매수 진행 — sleep 없이 완료.
    monkeypatch.setattr("src.order_executor.time.sleep", lambda _: None)
    kis = FakeKis(holdings={"GLDM": 4}, cash=1000.0, price=300.0, sll_ruse_seq=[0.0])
    _exec(kis).execute("NASDAQ")
    assert kis.sll_ruse_calls == 1  # 매도 후 1회 조회


def test_settlement_polls_until_zero(monkeypatch):
    # sll_ruse_amt 가 양수 → 0 순서로 반환되면 두 번 조회 후 매수.
    monkeypatch.setattr("src.order_executor.time.sleep", lambda _: None)
    kis = FakeKis(holdings={"GLDM": 4}, cash=1000.0, price=300.0, sll_ruse_seq=[500.0, 0.0])
    _exec(kis).execute("NASDAQ")
    assert kis.sll_ruse_calls == 2
    assert ("QQQM", "BUY", 3) in kis.orders


def test_settlement_not_called_without_sell(monkeypatch):
    # 매도 없는 경우(현금→매수)엔 정산 대기 호출 없음.
    monkeypatch.setattr("src.order_executor.time.sleep", lambda _: None)
    kis = FakeKis(holdings={}, cash=1000.0, price=300.0)
    _exec(kis).execute("NASDAQ")
    assert kis.sll_ruse_calls == 0


def test_settlement_timeout_proceeds_to_buy(monkeypatch):
    # timeout 초과 시에도 매수는 강행된다.
    monkeypatch.setattr("src.order_executor.time.sleep", lambda _: None)
    monkeypatch.setattr("src.order_executor._SETTLE_TIMEOUT", 0.0)  # 즉시 만료
    kis = FakeKis(holdings={"GLDM": 4}, cash=1000.0, price=300.0, sll_ruse_seq=[999.0] * 30)
    _exec(kis).execute("NASDAQ")
    assert ("QQQM", "BUY", 3) in kis.orders
