"""TradingCalendar — 미국 증시 거래일 판정 순수 함수 테스트.

외부 행동(날짜 입력 → bool)만 검증한다. 휴장일 날짜는 NYSE 공식 캘린더 기준.
"""
from datetime import date

from src.trading_calendar import is_trading_day


def test_regular_weekday_is_trading_day():
    # 평범한 평일(2026-06-17 수)은 거래일.
    assert is_trading_day(date(2026, 6, 17)) is True


def test_weekend_is_not_trading_day():
    assert is_trading_day(date(2026, 6, 20)) is False   # 토요일
    assert is_trading_day(date(2026, 6, 21)) is False   # 일요일


def test_major_holidays_are_not_trading_days():
    holidays = [
        date(2026, 1, 1),    # New Year's Day
        date(2026, 1, 19),   # MLK Day
        date(2026, 2, 16),   # Presidents Day
        date(2026, 4, 3),    # Good Friday
        date(2026, 5, 25),   # Memorial Day
        date(2026, 6, 19),   # Juneteenth
        date(2026, 9, 7),    # Labor Day
        date(2026, 11, 26),  # Thanksgiving
        date(2026, 12, 25),  # Christmas
    ]
    for d in holidays:
        assert is_trading_day(d) is False, d


def test_weekday_right_after_holiday_is_trading_day():
    # 휴장일 직후 평일은 거래일.
    assert is_trading_day(date(2026, 11, 27)) is True    # 추수감사절 다음날(half-day지만 거래일)
    assert is_trading_day(date(2026, 12, 28)) is True    # 크리스마스(금) 이후 첫 평일(월)
    assert is_trading_day(date(2026, 1, 2)) is True      # 신정 다음날(금)


def test_saturday_holiday_observed_on_preceding_friday():
    # Independence Day 2026: 7/4 토 → 7/3 금 휴장. 금요일(평일)인데도 비거래일.
    assert date(2026, 7, 3).weekday() == 4               # 금요일임을 확인
    assert is_trading_day(date(2026, 7, 3)) is False
    # Christmas 2027: 12/25 토 → 12/24 금 휴장.
    assert is_trading_day(date(2027, 12, 24)) is False


def test_sunday_holiday_observed_on_following_monday():
    # Independence Day 2027: 7/4 일 → 7/5 월 휴장. 월요일(평일)인데도 비거래일.
    assert date(2027, 7, 5).weekday() == 0               # 월요일임을 확인
    assert is_trading_day(date(2027, 7, 5)) is False


def test_new_year_on_saturday_does_not_close_preceding_friday():
    # 신정 예외: 2028-01-01 은 토요일 → NYSE 는 전년 12/31(금)을 쉬지 않는다.
    assert is_trading_day(date(2027, 12, 31)) is True    # 거래일(휴장 아님)
    assert is_trading_day(date(2028, 1, 1)) is False     # 토요일이라 비거래일(주말)


def test_holidays_across_all_covered_years():
    # 연도별 대표 휴장일이 테이블에 빠짐없이 들어있는지(2026~2030).
    samples = [
        date(2027, 11, 25),  # Thanksgiving 2027
        date(2028, 4, 14),   # Good Friday 2028
        date(2029, 6, 19),   # Juneteenth 2029
        date(2030, 5, 27),   # Memorial Day 2030
        date(2030, 12, 25),  # Christmas 2030
    ]
    for d in samples:
        assert is_trading_day(d) is False, d
