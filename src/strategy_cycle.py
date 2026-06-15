"""전략 사이클 오케스트레이터 — 모든 Phase B 모듈을 조립한다(Cron이 호출).

실행 순서(PRD/이슈 #8):
  1) is_paused 확인 → True면 알림 후 종료
  2) TokenManager로 토큰 발급(사이클 1회)
  3) MarketDataProvider로 월말 종가 조회 → 이상치면 승인 보류
  4) MomentumEngine으로 신호 산출 → 직전 신호와 동일이면 무거래
  5) OrderExecutor로 2-leg 전환 → PartialFillHandler로 체결 정산
  6) 사후 체결 보고(모드 태그는 notify=TelegramBot.send_message가 주입)

httpx/psycopg 등 무거운 의존성을 import 하지 않는다 — 협력자를 주입받아 mock 통합 테스트가 가능하다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

from .momentum import decide_signal

PAUSED = "PAUSED"
OUTLIER_PENDING = "OUTLIER_PENDING"
UNCHANGED = "UNCHANGED"
EXECUTED = "EXECUTED"
INCOMPLETE = "INCOMPLETE"


@dataclass
class CycleResult:
    status: str
    target: Optional[str] = None
    detail: str = ""


@dataclass
class CycleDeps:
    store: object                      # is_paused/get_last_signal/set_last_signal/record_trade/get_trading_mode
    notify: Callable[[str], None]      # TelegramBot.send_message (모드 태그 주입 지점)
    token_manager: object              # get_token()
    market_data: object                # get(symbol, months) -> MarketData
    positions: object                  # snapshot() -> Position(holdings, cash)
    order_executor: object             # execute(target) -> TransitionResult
    fill_handler: object               # settle(transition) -> SettlementReport
    fallback: object                   # on_incomplete_fill()
    approvals: Optional[object] = None  # request(kind, signal, ...)
    mode: str = "virtual"
    months: int = 13
    now: Callable[[], datetime] = datetime.now


def _format_report(target: str, transition, before, after, now: datetime) -> str:
    lines = [f"✅ {now.strftime('%Y-%m')} 신호: {target} 전환 완료"]
    for leg in transition.legs:
        if not leg.placed:
            continue
        verb = "매도" if leg.side == "SELL" else "매수"
        lines.append(f"  {verb}: {leg.symbol} {leg.quantity}주 (접수)")
    lines.append(f"  잔고: ${before.cash} → ${after.cash}")
    return "\n".join(lines)


def run_cycle(deps: CycleDeps) -> CycleResult:
    # 1) 일시정지 게이트
    if deps.store.is_paused():
        deps.notify("⏸️ 자동거래 일시정지 중 — 이번 월말 사이클을 건너뜁니다.")
        return CycleResult(PAUSED)

    # 2) 토큰 발급(사이클 1회 — 이후 재사용)
    deps.token_manager.get_token()

    # 3) 시세 조회 + 이상치 점검
    nasdaq = deps.market_data.get("QQQM", deps.months)
    gold = deps.market_data.get("GLDM", deps.months)
    if nasdaq.outliers or gold.outliers:
        deps.notify(
            f"⚠️ 모멘텀 이상치 감지 — 승인 전까지 자동 거래를 보류합니다. "
            f"(QQQM:{nasdaq.outliers}, GLDM:{gold.outliers})"
        )
        if deps.approvals is not None:
            deps.approvals.request("outlier", "PENDING", ttl_seconds=12 * 3600, rerequestable=False)
        return CycleResult(OUTLIER_PENDING)

    # 4) 신호 산출 + 직전 신호 비교
    signal = decide_signal(nasdaq.month_end_closes, gold.month_end_closes)
    last = deps.store.get_last_signal()
    deps.store.set_last_signal(signal.target, signal.score_nasdaq, signal.score_gold)
    if last == signal.target:
        deps.notify(f"ℹ️ {deps.now().strftime('%Y-%m')} 신호 변동 없음: {signal.target} 유지 — 무거래.")
        return CycleResult(UNCHANGED, target=signal.target)

    # 5) 2-leg 전환 + 체결 정산
    before = deps.positions.snapshot()
    transition = deps.order_executor.execute(signal.target)
    settlement = deps.fill_handler.settle(transition)
    if not settlement.complete:
        deps.fallback.on_incomplete_fill()
        return CycleResult(INCOMPLETE, target=signal.target)

    # 6) 사후 체결 보고 + 거래 로그
    after = deps.positions.snapshot()
    deps.store.record_trade(
        mode=deps.mode,
        signal=signal.target,
        legs=transition.legs,
        balance_before=before.cash,
        balance_after=after.cash,
    )
    deps.notify(_format_report(signal.target, transition, before, after, deps.now()))
    return CycleResult(EXECUTED, target=signal.target)
