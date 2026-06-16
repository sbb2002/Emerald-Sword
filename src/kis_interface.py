"""KIS 클라이언트의 인터페이스(Protocol)와 데이터 구조.

이 모듈은 httpx 등 무거운 의존성을 import 하지 않는다 — 로직 모듈
(TokenManager·PositionService·MarketDataProvider·OrderExecutor)이 타입 힌트로 쓰고,
테스트는 이 인터페이스를 만족하는 가짜 객체를 주입한다.
실제 구현(httpx)은 kis_client.HttpKisClient 이며 엔트리포인트에서만 import 한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass(frozen=True)
class TokenInfo:
    access_token: str
    expires_at: float  # epoch seconds


@dataclass(frozen=True)
class OrderResult:
    order_id: str
    symbol: str
    side: str  # BUY | SELL
    quantity: int
    accepted: bool
    raw: Optional[dict] = None


@dataclass(frozen=True)
class Execution:
    order_id: str
    symbol: str
    side: str
    filled_qty: int
    avg_price: float


@dataclass(frozen=True)
class DailyClose:
    date: str  # YYYY-MM-DD
    close: float


class KisClient(Protocol):
    """OrderExecutor·PositionService 등이 의존하는 KIS 읽기/쓰기 인터페이스."""

    def issue_token(self) -> TokenInfo: ...

    # 읽기
    def get_holdings(self) -> dict: ...        # {symbol: quantity}
    def get_cash(self) -> float: ...           # 주문 가능 현금(USD)
    def get_price(self, symbol: str) -> float: ...
    def get_buyable_qty(self, symbol: str, price: float) -> int: ...  # KIS 계산 최대 주문가능 수량
    def get_daily_closes(self, symbol: str, count: int) -> list: ...  # [DailyClose] 최신순

    # 쓰기/주문
    def place_order(self, symbol: str, side: str, quantity: int) -> OrderResult: ...
    def get_open_orders(self) -> list: ...     # [OrderResult] 미체결
    def get_executions(self, order_id: str) -> Execution: ...
