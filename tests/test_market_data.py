"""MarketDataProvider — 월말 종가 추출(결측 폴백) + 이상치 감지."""
from src.kis_interface import DailyClose
from src.market_data import MarketDataProvider, detect_outliers, month_end_series


def dc(date, close):
    return DailyClose(date=date, close=close)


def test_month_end_picks_last_trading_day_per_month():
    # 1/31 데이터 없음 → 1/30이 월말로 선택(직전 거래일 폴백 효과)
    daily = [dc("2025-01-29", 100), dc("2025-01-30", 101), dc("2025-02-26", 109), dc("2025-02-27", 110)]
    assert month_end_series(daily) == [("2025-01", 101.0), ("2025-02", 110.0)]


def test_detect_outliers_flags_large_jump():
    daily = [dc("2025-01-02", 100), dc("2025-01-03", 101), dc("2025-01-06", 200)]  # +98%
    assert detect_outliers(daily, 0.5) == ["2025-01-06"]


def test_no_outlier_under_threshold():
    daily = [dc("2025-01-02", 100), dc("2025-01-03", 110)]  # +10%
    assert detect_outliers(daily, 0.5) == []


class FakeKis:
    def __init__(self, daily):
        self._daily = daily

    def get_daily_closes(self, symbol, count):
        return list(self._daily)


def test_provider_returns_chronological_closes():
    daily = [dc("2025-03-31", 120), dc("2025-01-31", 100), dc("2025-02-28", 110)]
    provider = MarketDataProvider(FakeKis(daily))
    md = provider.get("QQQM", months=3)
    assert md.month_end_closes == [100.0, 110.0, 120.0]
