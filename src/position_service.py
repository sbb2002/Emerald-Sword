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

    def held_quantity(self, symbol: str) -> int:
        return int(self._client.get_holdings().get(symbol, 0))

    def cash(self) -> float:
        return self._client.get_cash()
