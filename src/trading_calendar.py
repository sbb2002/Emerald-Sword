"""TradingCalendar — 미국 증시 거래일 판정 (외부 의존성 없는 순수 함수).

Cron 이 월말 자정 부근에 깨어날 때, 그날이 미국 증시(NYSE/NASDAQ) 거래일인지
확인하는 데 쓴다. 주말·휴장일이면 사이클을 건너뛰어 불필요한 KIS 토큰 발급/주문을 막는다.

이 모듈은 momentum.py 처럼 KIS·텔레그램·DB 등 어떤 외부 의존성도 갖지 않는다.
pandas / pandas_market_calendars 같은 무거운 라이브러리를 쓰지 않고, 휴장일을
아래 상수 테이블에 직접 하드코딩한다(경량 방식을 명시적으로 선택).

휴장일 출처: NYSE 공식 휴장일 캘린더(https://www.nyse.com/markets/hours-calendars).
관측일 규칙(고정일 휴일에만 적용):
  - 토요일에 걸리면 → 직전 금요일 휴장
  - 일요일에 걸리면 → 다음 월요일 휴장
  단, 신정(1/1)이 토요일이면 NYSE 는 직전 금요일(전년 12/31)을 쉬지 않는다(예외).
월요일 기준 휴일(MLK·Presidents·Memorial·Labor)·목요일 기준(Thanksgiving)·
Good Friday 는 주말에 걸릴 수 없어 관측일 규칙이 필요 없다.

⚠️ 매년 갱신 필요: 아래 테이블은 2026~2030 만 담는다. 매년 NYSE 발표를 보고
다음 연도를 추가하라(특히 Good Friday 는 부활절 기준이라 해마다 날짜가 바뀐다).
정규 휴장일만 포함하고, 조기 폐장(half-day: 추수감사절 다음날 등)은 거래일로 본다.
"""
from __future__ import annotations

from datetime import date

# 아래 날짜는 모두 '관측일'(실제 휴장하는 날) 기준이다.
# 검증: NYSE 공식 캘린더 및 부활절(Good Friday) 알고리즘으로 대조 완료.
US_MARKET_HOLIDAYS: frozenset[date] = frozenset({
    # --- 2026 ---
    date(2026, 1, 1),    # New Year's Day (Thu)
    date(2026, 1, 19),   # Martin Luther King Jr. Day (3rd Mon Jan)
    date(2026, 2, 16),   # Washington's Birthday / Presidents Day (3rd Mon Feb)
    date(2026, 4, 3),    # Good Friday
    date(2026, 5, 25),   # Memorial Day (last Mon May)
    date(2026, 6, 19),   # Juneteenth (Fri)
    date(2026, 7, 3),    # Independence Day 관측(7/4 토 → 직전 금)
    date(2026, 9, 7),    # Labor Day (1st Mon Sep)
    date(2026, 11, 26),  # Thanksgiving (4th Thu Nov)
    date(2026, 12, 25),  # Christmas (Fri)
    # --- 2027 ---
    date(2027, 1, 1),    # New Year's Day (Fri)
    date(2027, 1, 18),   # MLK Day
    date(2027, 2, 15),   # Presidents Day
    date(2027, 3, 26),   # Good Friday
    date(2027, 5, 31),   # Memorial Day
    date(2027, 6, 18),   # Juneteenth 관측(6/19 토 → 직전 금)
    date(2027, 7, 5),    # Independence Day 관측(7/4 일 → 다음 월)
    date(2027, 9, 6),    # Labor Day
    date(2027, 11, 25),  # Thanksgiving
    date(2027, 12, 24),  # Christmas 관측(12/25 토 → 직전 금)
    # --- 2028 ---
    # New Year's Day(1/1)는 토요일 → NYSE 예외로 전년 12/31 을 쉬지 않으므로 휴장일 없음.
    date(2028, 1, 17),   # MLK Day
    date(2028, 2, 21),   # Presidents Day
    date(2028, 4, 14),   # Good Friday
    date(2028, 5, 29),   # Memorial Day
    date(2028, 6, 19),   # Juneteenth (Mon)
    date(2028, 7, 4),    # Independence Day (Tue)
    date(2028, 9, 4),    # Labor Day
    date(2028, 11, 23),  # Thanksgiving
    date(2028, 12, 25),  # Christmas (Mon)
    # --- 2029 ---
    date(2029, 1, 1),    # New Year's Day (Mon)
    date(2029, 1, 15),   # MLK Day
    date(2029, 2, 19),   # Presidents Day
    date(2029, 3, 30),   # Good Friday
    date(2029, 5, 28),   # Memorial Day
    date(2029, 6, 19),   # Juneteenth (Tue)
    date(2029, 7, 4),    # Independence Day (Wed)
    date(2029, 9, 3),    # Labor Day
    date(2029, 11, 22),  # Thanksgiving
    date(2029, 12, 25),  # Christmas (Tue)
    # --- 2030 ---
    date(2030, 1, 1),    # New Year's Day (Tue)
    date(2030, 1, 21),   # MLK Day
    date(2030, 2, 18),   # Presidents Day
    date(2030, 4, 19),   # Good Friday
    date(2030, 5, 27),   # Memorial Day
    date(2030, 6, 19),   # Juneteenth (Wed)
    date(2030, 7, 4),    # Independence Day (Thu)
    date(2030, 9, 2),    # Labor Day
    date(2030, 11, 28),  # Thanksgiving
    date(2030, 12, 25),  # Christmas (Wed)
})

# 테이블이 보장하는 연도 범위 — 이 밖이면 휴장일을 알 수 없다(아래 주석 참고).
_COVERED_YEARS = range(2026, 2031)


def is_trading_day(d: date) -> bool:
    """주어진 날짜가 미국 증시 거래일이면 True.

    토·일이면 False. 휴장일 테이블에 있으면 False. 그 외에는 True.

    주의: 테이블이 담지 않는 연도(2026~2030 밖)는 주말만 거를 수 있고 공휴일은
    알 수 없다 — 평일이면 True 를 반환한다. 매년 테이블을 갱신해 범위를 넓혀라.
    """
    if d.weekday() >= 5:          # 5=토, 6=일
        return False
    if d in US_MARKET_HOLIDAYS:
        return False
    return True
