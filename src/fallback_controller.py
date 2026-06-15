"""FallbackController — 장애·예외 분기 오케스트레이션 + 텔레그램 알림.

다루는 폴백:
  - 서버/KIS 장애: 알림 + 6시간 후 재시도
  - 휴장/응답 불가: 2시간 간격 N회(기본 3) 재시도, 모두 실패 시 휴장으로 간주(No-action)
  - 잔고 부족: 다음 거래에 부족하면 알림(수동 환전 유도), No-action
  - 부분/미체결 거래: 알림 후 재확인(재시도)

각 분기는 FallbackDecision(행동·재시도간격·사유)을 반환하고, 필요한 알림을 notifier로 보낸다.
재시도는 토큰 재발급을 유발하지 않는다(TokenManager가 기존 토큰 재사용 — KIS 분당 1회 제한).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

SIX_HOURS = 6 * 3600
TWO_HOURS = 2 * 3600

# 행동 코드
RETRY = "RETRY"
HOLIDAY = "HOLIDAY"
NO_ACTION = "NO_ACTION"
PROCEED = "PROCEED"


@dataclass(frozen=True)
class FallbackDecision:
    action: str
    retry_after_seconds: float = 0.0
    reason: str = ""


class FallbackController:
    def __init__(self, notifier: Callable[[str], None], *, max_market_retries: int = 3) -> None:
        self._notify = notifier
        self._max_market_retries = max_market_retries

    def on_server_failure(self, attempt: int = 1) -> FallbackDecision:
        self._notify("⚠️ 서버/KIS API 장애 — 6시간 후 재시도합니다.")
        return FallbackDecision(RETRY, SIX_HOURS, "server_failure")

    def on_market_closed(self, attempt: int) -> FallbackDecision:
        """attempt = 지금까지의 확인 실패 횟수(1부터). max 이하면 2h 재시도, 초과면 휴장 간주."""
        if attempt <= self._max_market_retries:
            self._notify(f"⚠️ 휴장/응답 불가 — 2시간 후 재시도 ({attempt}/{self._max_market_retries}).")
            return FallbackDecision(RETRY, TWO_HOURS, "market_check_retry")
        self._notify("ℹ️ 재시도 모두 실패 — 휴장으로 간주하고 이번 사이클은 No-action 합니다.")
        return FallbackDecision(HOLIDAY, 0.0, "treated_as_holiday")

    def check_balance(self, cash: float, needed: float) -> FallbackDecision:
        if cash < needed:
            self._notify(f"⚠️ 다음 거래 시 잔고 부족 예상 (필요 ${needed}, 보유 ${cash}). 수동 환전으로 충전해 주세요.")
            return FallbackDecision(NO_ACTION, 0.0, "insufficient_balance")
        return FallbackDecision(PROCEED, 0.0, "balance_ok")

    def on_incomplete_fill(self, reason: str = "incomplete_fill") -> FallbackDecision:
        self._notify("⚠️ 부분/미체결 거래 감지 — 재확인이 필요합니다.")
        return FallbackDecision(RETRY, 0.0, reason)
