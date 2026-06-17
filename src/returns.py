"""수익률 계산 — TWR(시간가중) + CAGR(연율화). 순수 함수, 외부 의존성 없음.

입출금이 있는 계좌의 '전략 성과'를 입금 타이밍 영향 없이 측정한다
(momentum.py 처럼 외부 의존 없는 순수 계산 — 단위 테스트로 검증).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Sequence


@dataclass(frozen=True)
class CashFlow:
    """입출금 한 건(수익률 계산용 뷰). signed_amount: 입금 +, 출금 −."""

    occurred_at: datetime
    signed_amount: float
    nav_before: float       # 입출금 직전 총자산(USD) — TWR 구간 분할 기준


def compute_twr(flows: Sequence[CashFlow], current_nav: float) -> Optional[float]:
    """시간가중수익률. 입출금 시점으로 구간을 나눠 각 구간 성장배수를 곱한다.

    각 구간 k: V_start = nav_before_k + signed_amount_k (입출금 직후),
               V_end   = 다음 입출금의 nav_before (없으면 current_nav).
    입출금 타이밍·규모와 무관한 순수 운용 성과를 준다. flows 가 비면 None.
    """
    if not flows:
        return None
    ordered = sorted(flows, key=lambda f: f.occurred_at)
    growth = 1.0
    for i, f in enumerate(ordered):
        v_start = f.nav_before + f.signed_amount
        v_end = ordered[i + 1].nav_before if i + 1 < len(ordered) else current_nav
        if v_start <= 0:
            continue  # 전액 출금 등 비정상 구간 — 방어적으로 건너뛴다
        growth *= v_end / v_start
    return growth - 1.0


def compute_cagr(twr: Optional[float], start: datetime, now: datetime) -> Optional[float]:
    """TWR 을 연율화한 복리수익률. 운용 365일 미만이면 None(짧은 기간 연율화 왜곡 방지)."""
    if twr is None:
        return None
    days = (now - start).days
    if days < 365:
        return None
    years = days / 365.25
    return (1.0 + twr) ** (1.0 / years) - 1.0


def running_days(flows: Sequence[CashFlow], now: datetime) -> Optional[int]:
    """첫 입금(시드)일로부터 경과 일수 — CAGR 숨김 시 '운용 N개월' 안내용."""
    if not flows:
        return None
    start = min(f.occurred_at for f in flows)
    return max(0, (now - start).days)
