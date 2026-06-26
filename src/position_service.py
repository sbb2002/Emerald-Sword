"""PositionService — 실시간 잔고 조회 (상태 비저장).

현재 보유 자산·수량·현금을 매번 KIS API로 실시간 조회한다.
봇 내부에 포지션을 캐시하지 않는다(실제 잔고가 단일 진실 원천 — CLAUDE.md).
"""
from __future__ import annotations

from dataclasses import dataclass

from .kis_interface import KisClient


@dataclass(frozen=True)
class Position:
    holdings: dict  # {symbol: quantity}
    cash: float


class PositionService:
    def __init__(self, client: KisClient) -> None:
        self._client = client

    def snapshot(self) -> Position:
        # 캐시 없음 — 호출마다 실시간 조회
        return Position(holdings=dict(self._client.get_holdings()), cash=self._client.get_cash())

    def value_holdings(self, holdings: dict) -> float:
        """보유 dict 를 현재가로 평가한 합계(USD). 가격 조회 실패 종목은 0 평가(보수적).

        총자산(NAV)=value_holdings(holdings)+cash. 통화 모호성이 없어, 원화 자동환전
        모의계좌에서 주문가능 외화현금(get_cash)만으로는 어긋나 보이던 '잔고'를 보완한다.
        """
        total = 0.0
        for sym, qty in holdings.items():
            try:
                px = self._client.get_price(sym)
            except Exception:
                px = 0.0
            if px and px > 0:
                total += qty * px
        return total

    def nav(self) -> float:
        """현재 총자산(USD) = 보유 평가금액 + 주문가능현금."""
        snap = self.snapshot()
        return snap.cash + self.value_holdings(snap.holdings)

    def held_quantity(self, symbol: str) -> int:
        return int(self._client.get_holdings().get(symbol, 0))

    def cash(self) -> float:
        return self._client.get_cash()
