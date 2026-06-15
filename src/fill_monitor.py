"""PartialFillHandler — 부분 체결 감지 + 재시도.

2-leg 전환 후 각 leg의 체결 수량을 조회해, 미체결/부분 체결이면 잔여 수량을
최대 N회 재주문한다(한쪽 leg만 체결돼 현금만 붕 뜨는 상태 방지).
최종적으로도 미완료면 SettlementReport.complete=False 로 보고해 상위(cron)가 알림한다.

재시도는 토큰을 재발급하지 않는다(TokenManager가 기존 토큰 재사용 — KIS 분당 1회 제한).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .kis_interface import KisClient
from .order_executor import TransitionResult


@dataclass
class LegSettlement:
    symbol: str
    side: str
    ordered_qty: int
    filled_qty: int

    @property
    def remaining(self) -> int:
        return max(self.ordered_qty - self.filled_qty, 0)

    @property
    def complete(self) -> bool:
        return self.remaining == 0


@dataclass
class SettlementReport:
    legs: list
    retries_used: int

    @property
    def complete(self) -> bool:
        return all(leg.complete for leg in self.legs)

    @property
    def incomplete(self) -> list:
        return [leg for leg in self.legs if not leg.complete]


class PartialFillHandler:
    def __init__(
        self,
        client: KisClient,
        *,
        max_retries: int = 3,
        retry_wait: float = 0.0,
        sleep: Callable[[float], None] = lambda s: None,
    ) -> None:
        self._client = client
        self._max_retries = max_retries
        self._retry_wait = retry_wait
        self._sleep = sleep

    def _filled(self, order_id: str) -> int:
        try:
            return int(self._client.get_executions(order_id).filled_qty)
        except Exception:
            return 0

    def settle(self, transition: TransitionResult) -> SettlementReport:
        legs: dict = {}
        for leg in transition.placed_orders:
            if leg.order is None:
                continue
            key = (leg.symbol, leg.side)
            legs[key] = LegSettlement(leg.symbol, leg.side, leg.quantity, self._filled(leg.order.order_id))

        retries = 0
        while retries < self._max_retries and any(not leg.complete for leg in legs.values()):
            retries += 1
            self._sleep(self._retry_wait)
            for key, ls in list(legs.items()):
                if ls.complete:
                    continue
                new_order = self._client.place_order(ls.symbol, ls.side, ls.remaining)
                added = self._filled(new_order.order_id)
                legs[key] = LegSettlement(ls.symbol, ls.side, ls.ordered_qty, ls.filled_qty + added)

        return SettlementReport(legs=list(legs.values()), retries_used=retries)
