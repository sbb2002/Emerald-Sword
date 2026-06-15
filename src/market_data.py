"""MarketDataProvider — KIS 시세 조회 + 결측 폴백 + 이상치 감지.

월말 종가 시계열을 만들어 MomentumEngine 에 공급한다.

결측 폴백: "각 달의 마지막 거래일 종가"를 월말 종가로 삼으면, 실제 말일에 데이터가
없을 때 자동으로 그 달의 직전 거래일 종가가 선택된다(직전 거래일 탐색과 동일 효과).
이상치 감지: 전일 대비 변동이 임계(기본 ±50%)를 넘으면 해당 날짜를 플래그한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .kis_interface import DailyClose, KisClient

DEFAULT_OUTLIER_THRESHOLD = 0.5  # 전일 대비 ±50%


@dataclass(frozen=True)
class MarketData:
    month_end_closes: list  # 오름차순(과거→현재) float
    outliers: list          # 이상치로 플래그된 날짜(YYYY-MM-DD) 목록


def month_end_series(daily: Sequence[DailyClose]) -> list:
    """일별 종가 → 각 달의 마지막 거래일 종가 (YYYY-MM, close) 오름차순."""
    by_month: dict = {}
    for dc in daily:
        if not dc.date or len(dc.date) < 7:
            continue
        ym = dc.date[:7]
        prev = by_month.get(ym)
        if prev is None or dc.date > prev[0]:
            by_month[ym] = (dc.date, dc.close)
    return [(ym, by_month[ym][1]) for ym in sorted(by_month)]


def detect_outliers(daily: Sequence[DailyClose], threshold: float = DEFAULT_OUTLIER_THRESHOLD) -> list:
    """전일 대비 |변동률| > threshold 인 날짜를 플래그한다."""
    ordered = sorted((dc for dc in daily if dc.date), key=lambda d: d.date)
    flagged = []
    for prev, cur in zip(ordered, ordered[1:]):
        if prev.close > 0 and abs(cur.close / prev.close - 1.0) > threshold:
            flagged.append(cur.date)
    return flagged


class MarketDataProvider:
    def __init__(
        self,
        client: KisClient,
        *,
        outlier_threshold: float = DEFAULT_OUTLIER_THRESHOLD,
        trading_days_per_month: int = 23,
    ) -> None:
        self._client = client
        self._threshold = outlier_threshold
        self._tdpm = trading_days_per_month

    def get(self, symbol: str, months: int) -> MarketData:
        count = (months + 1) * self._tdpm + 10  # 월말 추출용 여유분
        daily = self._client.get_daily_closes(symbol, count)
        series = month_end_series(daily)
        closes = [c for _, c in series][-months:]
        outliers = detect_outliers(daily, self._threshold)
        return MarketData(month_end_closes=closes, outliers=outliers)
