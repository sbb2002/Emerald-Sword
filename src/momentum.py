"""MomentumEngine — 전략의 두뇌 (외부 의존성 없는 순수 함수).

입력: 나스닥100·금의 월말 종가 시계열(과거→현재, 마지막 원소가 기준 시점 t).
처리: 각 자산의 3·6·12개월 수익률을 단순 평균해 모멘텀 점수 산출.
출력: NASDAQ | GOLD | CASH (둘 다 점수 <= 0이면 CASH, 아니면 argmax).
실행 매핑(OrderExecutor 담당): NASDAQ → QQQM, GOLD → GLDM, CASH → 미보유.

이 모듈은 KIS·텔레그램·DB 등 어떤 외부 의존성도 갖지 않는다 — 값만 주입받아 계산한다.
입력의 결측 보정(직전 거래일 대체)은 MarketDataProvider(#5)의 책임이며, 여기서는
이미 보정된 종가를 그대로 받는다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

NASDAQ = "NASDAQ"
GOLD = "GOLD"
CASH = "CASH"

# 모멘텀 점수에 쓰는 룩백(개월). PRD에서 3·6·12로 확정.
LOOKBACK_MONTHS: tuple[int, ...] = (3, 6, 12)


@dataclass(frozen=True)
class SignalResult:
    target: str          # NASDAQ | GOLD | CASH
    score_nasdaq: float
    score_gold: float


def momentum_score(
    prices: Sequence[float],
    lookbacks: Sequence[int] = LOOKBACK_MONTHS,
) -> float:
    """월말 종가 시계열로 모멘텀 점수 = mean(r_3m, r_6m, r_12m) 를 구한다.

    prices[-1]      = 기준 시점 t 의 월말 종가
    prices[-1 - N]  = N개월 전 월말 종가
    r_Nm = prices[-1] / prices[-1 - N] - 1
    """
    need = max(lookbacks) + 1
    if len(prices) < need:
        raise ValueError(f"월말 종가가 최소 {need}개 필요합니다 (받은 개수: {len(prices)}).")

    latest = prices[-1]
    if latest <= 0:
        raise ValueError("기준 시점 종가는 양수여야 합니다.")

    returns: list[float] = []
    for n in lookbacks:
        past = prices[-1 - n]
        if past <= 0:
            raise ValueError(f"{n}개월 전 종가는 양수여야 합니다.")
        returns.append(latest / past - 1.0)

    return sum(returns) / len(returns)


def _select(score_nasdaq: float, score_gold: float) -> str:
    """두 점수로 목표 자산을 고른다. 둘 다 <= 0 이면 CASH.

    동률(양수) 이면 NASDAQ 우선 — 결정론적 타이브레이크(실데이터에서 정확한 동률은 사실상 없음).
    """
    if max(score_nasdaq, score_gold) <= 0:
        return CASH
    return NASDAQ if score_nasdaq >= score_gold else GOLD


def decide_signal(
    nasdaq_prices: Sequence[float],
    gold_prices: Sequence[float],
    lookbacks: Sequence[int] = LOOKBACK_MONTHS,
) -> SignalResult:
    """나스닥100·금 월말 종가 시계열로 이번 신호(목표 자산 + 두 점수)를 결정한다."""
    score_nasdaq = momentum_score(nasdaq_prices, lookbacks)
    score_gold = momentum_score(gold_prices, lookbacks)
    return SignalResult(
        target=_select(score_nasdaq, score_gold),
        score_nasdaq=score_nasdaq,
        score_gold=score_gold,
    )
