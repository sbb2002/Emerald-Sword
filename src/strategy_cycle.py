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
from .order_executor import ALL_TICKERS, TICKER
from .trading_calendar import is_trading_day

PAUSED = "PAUSED"
NON_TRADING_DAY = "NON_TRADING_DAY"
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


def _leg_filled(leg, before, after) -> int:
    """주문 전·후 실보유 차이로 실제 체결 수량을 추정한다.

    KIS 실보유(get_holdings)가 단일 진실 원천 — 미검증 체결조회(inquire-ccnl) 없이
    after.holdings - before.holdings 로 체결량을 잡는다. 한 transition 안에서 종목이
    겹치지 않으므로(매도/매수가 서로 다른 종목) 종목별 차이가 곧 해당 leg 의 체결량이다.
    """
    b = int(before.holdings.get(leg.symbol, 0) or 0)
    a = int(after.holdings.get(leg.symbol, 0) or 0)
    moved = (a - b) if leg.side == "BUY" else (b - a)
    return max(0, min(moved, leg.quantity))


def _fmt_usd(value) -> str:
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return f"${value}"


def _format_report(target: str, transition, before, after, now: datetime,
                   nav_before=None, nav_after=None) -> str:
    # 접수(rt_cd=0)가 아니라 '실제 체결'을 보고한다 — 부분체결을 정직하게 알린다.
    rows = [(leg, _leg_filled(leg, before, after)) for leg in transition.placed_orders]
    fully = all(filled >= leg.quantity for leg, filled in rows)
    head = "전환 완료" if fully else "전환 — 일부 미체결"
    lines = [f"{'✅' if fully else '⚠️'} {now.strftime('%Y-%m')} 신호: {target} {head}"]
    for leg, filled in rows:
        verb = "매도" if leg.side == "SELL" else "매수"
        if filled >= leg.quantity:
            lines.append(f"  {verb}: {leg.symbol} {leg.quantity}주 체결 ✅")
        else:
            lines.append(f"  {verb}: {leg.symbol} {filled}/{leg.quantity}주 체결, {leg.quantity - filled}주 미체결 ⚠️")
    if not fully:
        lines.append("  ⚠️ 미체결분은 장중 자동체결 대기 → 장마감까지 안 되면 만료됩니다.")
    # 총자산(NAV)을 먼저, 현금을 그다음 — 원화 자동환전 모의계좌에서 현금(주문가능 외화현금)만
    # 보면 환전 전 매수여력이 빠져 어긋나 보이므로 통화 모호성 없는 총자산을 함께 표시한다.
    if nav_before is not None and nav_after is not None:
        lines.append(f"  총자산: {_fmt_usd(nav_before)} → {_fmt_usd(nav_after)}")
    lines.append(f"  현금: {_fmt_usd(before.cash)} → {_fmt_usd(after.cash)}")
    return "\n".join(lines)


def _already_at_target(target: str, holdings: dict) -> bool:
    """실제 보유가 목표 신호와 일치하는가 — 직전 신호가 아니라 '포지션'이 단일 진실 원천."""
    target_symbol = TICKER.get(target)  # CASH → None
    held = {s for s in ALL_TICKERS if int(holdings.get(s, 0) or 0) > 0}
    if target_symbol is None:           # CASH: 아무 종목도 보유하지 않아야 일치
        return not held
    return held == {target_symbol}      # 목표 종목만 정확히 보유


def run_cycle(deps: CycleDeps) -> CycleResult:
    # 1) 일시정지 게이트
    if deps.store.is_paused():
        deps.notify("⏸️ 자동거래 일시정지 중 — 이번 월말 사이클을 건너뜁니다.")
        return CycleResult(PAUSED)

    # 1.5) 거래일 게이트 — 비거래일(주말·미국 증시 휴장)이면 토큰 발급 전에 건너뛴다.
    #      deps.now()=datetime.now()=서버 UTC(cron.py 가 now 를 주입하지 않음). cron 트리거
    #      (UTC 30 15 28-31)는 UTC 15:30 = 미국 동부 오전(장중)이라 UTC 날짜가 미국 증시(ET)
    #      거래일과 일치한다. ⚠️ KST/tz-aware 로 바꾸면 하루 어긋나 정상 거래일을 스킵하니 UTC 유지.
    today = deps.now().date()
    if not is_trading_day(today):
        deps.notify(
            f"📅 {today.isoformat()} — 미국 증시 비거래일(주말·휴장)이라 이번 트리거를 건너뜁니다."
        )
        return CycleResult(NON_TRADING_DAY)

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

    # 4) 신호 산출 (last_signal 은 기록만 — 매매 판단은 아래 '실제 보유 포지션' 기준)
    signal = decide_signal(nasdaq.month_end_closes, gold.month_end_closes)
    deps.store.set_last_signal(signal.target, signal.score_nasdaq, signal.score_gold)

    # 5) 실제 보유가 이미 목표와 일치하면 무거래.
    #    직전 신호가 아니라 KIS 실보유를 기준으로 판단 → 크래시·중단에도 자가치유
    #    (실패한 사이클이 last_signal 만 남겨 이후 영구히 '무거래'가 되던 버그 방지).
    before = deps.positions.snapshot()
    if _already_at_target(signal.target, before.holdings):
        deps.notify(f"ℹ️ {deps.now().strftime('%Y-%m')} 신호 {signal.target} — 이미 목표 보유, 무거래.")
        return CycleResult(UNCHANGED, target=signal.target)

    # 5.5) 거래 전 총자산(NAV) — 보유를 현재가로 평가. 사후보고·/log 의 '총자산 변화' 기준.
    nav_before = before.cash + deps.positions.value_holdings(before.holdings)

    # 6) 2-leg 전환 + 체결 정산
    transition = deps.order_executor.execute(signal.target)
    settlement = deps.fill_handler.settle(transition)
    if not settlement.complete:
        deps.fallback.on_incomplete_fill()
        return CycleResult(INCOMPLETE, target=signal.target)

    # 7) 낸 주문이 하나도 없으면(예: 주문가능 현금 부족) '전환 완료'로 보고하지 않는다.
    if not transition.placed_orders:
        if any(leg.skipped_reason == "insufficient_cash" for leg in transition.legs):
            deps.notify(
                f"⚠️ {deps.now().strftime('%Y-%m')} 신호 {signal.target} — 주문가능 현금이 부족해 "
                f"매수하지 못했습니다. 계좌의 주문가능 잔고를 확인하세요."
            )
        else:
            deps.notify(f"ℹ️ {deps.now().strftime('%Y-%m')} 신호 {signal.target} — 낸 주문 없음(무거래).")
        return CycleResult(INCOMPLETE, target=signal.target)

    # 8) 사후 체결 보고 + 거래 로그
    after = deps.positions.snapshot()
    nav_after = after.cash + deps.positions.value_holdings(after.holdings)
    deps.store.record_trade(
        mode=deps.mode,
        signal=signal.target,
        legs=transition.legs,
        balance_before=before.cash,
        balance_after=after.cash,
        nav_before=nav_before,
        nav_after=nav_after,
    )
    deps.notify(_format_report(signal.target, transition, before, after, deps.now(),
                               nav_before=nav_before, nav_after=nav_after))
    return CycleResult(EXECUTED, target=signal.target)
