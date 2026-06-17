"""returns — TWR(시간가중) + CAGR 순수 함수 검증."""
from datetime import datetime

from src.returns import CashFlow, compute_cagr, compute_twr, running_days


def _cf(month, signed, nav_before):
    return CashFlow(occurred_at=datetime(2026, month, 1), signed_amount=signed, nav_before=nav_before)


def test_twr_none_when_no_flows():
    assert compute_twr([], 100.0) is None


def test_twr_single_seed_equals_simple_return():
    # 시드 $100k(nav_before=0) 하나 → 현재 NAV 98,379.94 → TWR = 단순 누적
    twr = compute_twr([_cf(1, 100000.0, 0.0)], 98379.94)
    assert abs(twr - (98379.94 / 100000.0 - 1.0)) < 1e-9


def test_twr_ignores_deposit_timing():
    # $100k → +10%($110k) → $100k 추가($210k) → 0%($210k)
    # 단순누적은 +5%지만 TWR 은 입금 타이밍을 제거해 +10%.
    flows = [_cf(1, 100000.0, 0.0), _cf(2, 100000.0, 110000.0)]
    assert abs(compute_twr(flows, 210000.0) - 0.10) < 1e-9


def test_twr_handles_withdrawal():
    # $100k → +20%($120k) → $50k 출금($70k) → 0%
    # 구간1 120/100=1.2, 구간2 70/(120−50)=1.0 → TWR +20%
    flows = [_cf(1, 100000.0, 0.0), _cf(2, -50000.0, 120000.0)]
    assert abs(compute_twr(flows, 70000.0) - 0.20) < 1e-9


def test_cagr_hidden_under_one_year():
    twr = compute_twr([_cf(1, 100000.0, 0.0)], 110000.0)
    assert compute_cagr(twr, datetime(2026, 1, 1), datetime(2026, 7, 1)) is None  # 6개월


def test_cagr_annualizes_over_one_year():
    # TWR +21% 를 약 2년에 → CAGR ≈ sqrt(1.21)−1 = 10%
    cagr = compute_cagr(0.21, datetime(2024, 1, 1), datetime(2026, 1, 1))
    assert cagr is not None and abs(cagr - 0.10) < 1e-3


def test_cagr_one_year_close_to_twr():
    cagr = compute_cagr(-0.0162, datetime(2025, 1, 1), datetime(2026, 1, 1))  # 365일
    assert cagr is not None and abs(cagr - (-0.0162)) < 1e-3


def test_cagr_none_when_twr_none():
    assert compute_cagr(None, datetime(2025, 1, 1), datetime(2026, 1, 1)) is None


def test_running_days():
    assert running_days([_cf(1, 100000.0, 0.0)], datetime(2026, 4, 1)) == 90
    assert running_days([], datetime(2026, 4, 1)) is None
