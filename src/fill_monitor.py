"""PartialFillHandler — 2-leg 주문의 '접수' 정산.

각 leg 의 접수 결과(accepted = KIS rt_cd=0)를 모아 보고한다.
하나라도 거부(accepted=False)면 SettlementReport.complete=False 가 되어
상위(strategy_cycle→cron)가 미완료로 알린다.

⚠️ 부분체결 자동재시도는 의도적으로 비활성화돼 있다.
   체결수량 조회(KisClient.get_executions)가 아직 스텁(항상 0 반환)이라,
   '체결량 기준 재주문'을 하면 접수된 주문을 미체결로 오판해 같은 주문을 다시 내
   '중복 매수'(실거래에서 의도의 2배)를 일으킨다. 실제 모의 트리거에서 동일 매수가
   2회 접수돼 현금이 소진된 바 있다(2026-06). 따라서 get_executions 를 KIS
   체결조회(inquire-ccnl)로 실제 구현한 뒤 '대기 → 체결확인 → 미체결분 취소 후
   재주문' 형태로 안전하게 복원한다. 그 전까지는 접수만 정산한다.
"""
from __future__ import annotations

from dataclasses import dataclass

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
    retries_used: int = 0

    @property
    def complete(self) -> bool:
        return all(leg.complete for leg in self.legs)

    @property
    def incomplete(self) -> list:
        return [leg for leg in self.legs if not leg.complete]


class PartialFillHandler:
    def __init__(self, client: KisClient) -> None:
        # client 는 부분체결 재시도(get_executions 구현 후) 복원 시 사용. 현재 settle 은 미사용.
        self._client = client

    def settle(self, transition: TransitionResult) -> SettlementReport:
        # 접수(accepted=rt_cd=0) 기준 정산 — 재주문하지 않는다(중복 주문 방지).
        # 접수된 leg 는 완료로, 거부된 leg 는 미완료(remaining>0)로 본다.
        legs: list = []
        for leg in transition.placed_orders:
            if leg.order is None:
                continue
            accepted = bool(getattr(leg.order, "accepted", False))
            filled = leg.quantity if accepted else 0
            legs.append(LegSettlement(leg.symbol, leg.side, leg.quantity, filled))
        return SettlementReport(legs=legs, retries_used=0)
