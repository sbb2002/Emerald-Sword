"""MomentumEngine 테스트 — 외부 의존(KIS·텔레그램·DB) 없이 순수 Python으로 실행된다.

검증 대상(인수 조건):
  1) 나스닥 우위 / 금 우위 / 둘 다 음수(CASH) / 동률
  2) historical_data.csv(없으면 합성 픽스처) 구간의 기대 신호 회귀 고정
  3) 결측 보정된 입력(직전 거래일 대체값)에서도 정상 동작
"""
import csv
from pathlib import Path

import pytest

from src.momentum import (
    CASH,
    GOLD,
    NASDAQ,
    SignalResult,
    decide_signal,
    momentum_score,
)

FIXTURE = Path(__file__).parent / "fixtures" / "momentum_sample.csv"
REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------- 핵심 4케이스 ----------

def test_nasdaq_wins():
    nasdaq = list(range(100, 113))          # 13개, 상승 → 양수
    gold = list(range(200, 187, -1))        # 13개, 하락 → 음수
    result = decide_signal(nasdaq, gold)
    assert result.target == NASDAQ
    assert result.score_nasdaq > 0
    assert result.score_gold < 0


def test_gold_wins():
    nasdaq = list(range(112, 99, -1))        # 하락 → 음수
    gold = list(range(100, 113))             # 상승 → 양수
    result = decide_signal(nasdaq, gold)
    assert result.target == GOLD
    assert result.score_gold > 0


def test_both_negative_returns_cash():
    nasdaq = list(range(112, 99, -1))        # 하락 → 음수
    gold = list(range(200, 187, -1))         # 하락 → 음수
    result = decide_signal(nasdaq, gold)
    assert result.target == CASH


def test_tie_prefers_nasdaq():
    series = list(range(100, 113))           # 동일 시계열 → 점수 동률(양수)
    result = decide_signal(series, list(series))
    assert result.score_nasdaq == result.score_gold
    assert result.score_nasdaq > 0
    assert result.target == NASDAQ           # 결정론적 타이브레이크


# ---------- 결측 보정된 입력 ----------

def test_substituted_value_is_used():
    # t-6 월말 데이터가 결측이라 직전 거래일 종가(110)로 보정됐다고 가정.
    # 엔진은 값의 출처를 따지지 않고 주어진 값으로 그대로 계산한다.
    prices = [100, 0, 0, 0, 0, 0, 110, 0, 0, 120, 0, 0, 130]  # 길이 13
    # 참조 인덱스: t=-1(130), t-3=-4(120), t-6=-7(110), t-12=-13(100)
    expected = ((130 / 120 - 1) + (130 / 110 - 1) + (130 / 100 - 1)) / 3
    assert momentum_score(prices) == pytest.approx(expected, abs=1e-9)


# ---------- 입력 검증 ----------

def test_insufficient_data_raises():
    with pytest.raises(ValueError):
        momentum_score([1.0] * 12)           # 최소 13개 필요


def test_non_positive_price_raises():
    with pytest.raises(ValueError):
        momentum_score([0.0] * 13)


def test_signal_result_type_and_scores():
    nasdaq = list(range(100, 113))
    gold = list(range(200, 187, -1))
    result = decide_signal(nasdaq, gold)
    assert isinstance(result, SignalResult)
    assert result.score_nasdaq == momentum_score(nasdaq)
    assert result.score_gold == momentum_score(gold)


# ---------- 회귀 테스트 (합성 픽스처: 기대 신호 고정) ----------

def _load_series(path: Path, date_col: str, n_col: str, g_col: str):
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    rows.sort(key=lambda r: r[date_col])
    nasdaq = [float(r[n_col]) for r in rows if r[n_col] not in (None, "")]
    gold = [float(r[g_col]) for r in rows if r[g_col] not in (None, "")]
    return nasdaq, gold


def test_regression_fixture_signal_is_nasdaq():
    nasdaq, gold = _load_series(FIXTURE, "date", "nasdaq", "gold")
    result = decide_signal(nasdaq, gold)
    # 손계산 고정값: 나스닥 상승·금 하락 → NASDAQ
    assert result.target == NASDAQ
    assert result.score_nasdaq == pytest.approx(0.18838384, abs=1e-6)
    assert result.score_gold == pytest.approx(-0.05086595, abs=1e-6)


# ---------- 실 historical_data.csv 자동 감지 (있으면 추가 검증, 없으면 skip) ----------

def _find_col(fieldnames, candidates):
    lower = {fn.lower(): fn for fn in (fieldnames or [])}
    for c in candidates:
        if c.lower() in lower:
            return lower[c.lower()]
    return None


def test_real_historical_csv_if_present():
    path = REPO_ROOT / "historical_data.csv"
    if not path.exists():
        pytest.skip("historical_data.csv 없음 — 합성 픽스처 회귀 테스트로 대체")

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fields = reader.fieldnames

    date_col = _find_col(fields, ["date", "month"])
    n_col = _find_col(fields, ["nasdaq", "qqqm", "qqq"])
    g_col = _find_col(fields, ["gold", "gldm", "gld"])
    if not (date_col and n_col and g_col):
        pytest.skip(f"컬럼 자동 감지 실패 (헤더: {fields})")

    nasdaq, gold = _load_series(path, date_col, n_col, g_col)
    if len(nasdaq) < 13 or len(gold) < 13:
        pytest.skip("월말 종가가 13개 미만")

    result = decide_signal(nasdaq, gold)
    assert result.target in (NASDAQ, GOLD, CASH)
    assert isinstance(result.score_nasdaq, float)
    assert isinstance(result.score_gold, float)
