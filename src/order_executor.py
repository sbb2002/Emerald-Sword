"""OrderExecutor — 2-leg 전환 + 멱등성 + 정수 주문 + 모드 분기.

매핑: NASDAQ → QQQM, GOLD → GLDM, CASH → 미보유(전량 매도).
2-leg: 목표가 아닌 보유 종목 전량 매도 → 목표 종목을 가용현금으로 정수 매수.

멱등성(주문 전 조회로 이중 주문 방지):
  - 목표 종목을 이미 보유 중이면 매수하지 않는다(재실행·동일 신호 churn 방지).
  - 같은 종목·방향의 미체결 주문이 있으면 재주문하지 않는다.
  - 현금이 1주 가격 미만이면 매수를 보류한다(자투리 현금 보유 — PRD).

모드 분기: KIS 클라이언트가 build_kis_client(mode)로 실전/모의 엔드포인트·계좌로 이미 구성된다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from .kis_interface import KisClient, OrderResult
from .position_service import PositionService

TICKER = {"NASDAQ": "QQQM", "GOLD": "GLDM"}
ALL_TICKERS = ("QQQM", "GLDM")


@dataclass
class Leg:
    side: str            # BUY | SELL
    symbol: str
    quantity: int
    placed: bool
    skipped_reason: str = ""
    order: Optional[OrderResult] = None


@dataclass
class TransitionResult:
    target: str                       # NASDAQ | GOLD | CASH
    target_symbol: Optional[str]      # QQQM | GLDM | None(CASH)
    legs: list
    complete: bool                    # 실제 낸 주문이 모두 접수됐는가

    @property
    def placed_orders(self) -> list:
        return [leg for leg in self.legs if leg.placed]


class OrderExecutor:
    def __init__(self, client: KisClient, positions: PositionService, mode: str = "virtual") -> None:
        self._client = client
        self._positions = positions
        self._mode = mode

    def _open_orders(self) -> list:
        try:
            return self._client.get_open_orders()
        except Exception:
            return []

    def execute(self, target: str) -> TransitionResult:
        if target not in ("NASDAQ", "GOLD", "CASH"):
            raise ValueError(f"알 수 없는 신호: {target}")

        target_symbol = TICKER.get(target)  # CASH → None
        holdings = self._positions.snapshot().holdings
        open_orders = self._open_orders()
        legs: list = []

        def has_open(symbol: str, side: str) -> bool:
            return any(o.symbol == symbol and o.side == side for o in open_orders)

        # 1) 매도 leg — 목표가 아닌 보유 종목 전량 매도
        for sym in ALL_TICKERS:
            qty = int(holdings.get(sym, 0))
            if sym == target_symbol or qty <= 0:
                continue
            if has_open(sym, "SELL"):
                legs.append(Leg("SELL", sym, qty, placed=False, skipped_reason="already_pending"))
                continue
            order = self._client.place_order(sym, "SELL", qty)
            legs.append(Leg("SELL", sym, qty, placed=True, order=order))

        # 2) 매수 leg — 목표 종목을 정수 수량으로 매수
        if target_symbol is not None:
            held_target = int(holdings.get(target_symbol, 0))
            if held_target > 0:
                # 이미 목표 보유 → 멱등(추가 매수·churn 없음)
                legs.append(Leg("BUY", target_symbol, held_target, placed=False, skipped_reason="already_holding_target"))
            elif has_open(target_symbol, "BUY"):
                legs.append(Leg("BUY", target_symbol, 0, placed=False, skipped_reason="already_pending"))
            else:
                cash = self._positions.cash()
                price = self._client.get_price(target_symbol)
                qty = int(math.floor(cash / price)) if price > 0 else 0
                if qty > 0:
                    order = self._client.place_order(target_symbol, "BUY", qty)
                    legs.append(Leg("BUY", target_symbol, qty, placed=True, order=order))
                else:
                    legs.append(Leg("BUY", target_symbol, 0, placed=False, skipped_reason="insufficient_cash"))

        placed = [leg for leg in legs if leg.placed]
        complete = all(leg.order is not None and leg.order.accepted for leg in placed)
        return TransitionResult(target=target, target_symbol=target_symbol, legs=legs, complete=complete)
