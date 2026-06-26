"""월말 전환(QQQM↔GLDM) 매도→매수 정산 타이밍 — 모의 전용 라이브 검증 스크립트.

문제(미검증 위험):
  order_executor.execute() 는 한 사이클에서 매도(place_order SELL, '접수'만)→1.1s→
  매수(get_buyable_qty=KIS max_ord_psbl_qty 기준)로 이어진다. KIS 가 미체결 매도대금을
  같은 사이클의 max_ord_psbl_qty 에 즉시 반영하지 않으면 신규 종목이 과소 매수된다.
  최악은 현금 ~$0 인 100% 보유 상태에서 0주 매수 → 매도만 되고 전환이 깨지는 것.
  (fill_monitor 도 '접수' 기준 정산이라 이 타이밍을 보정하지 못한다.)

  정기 월말 사이클은 이 시나리오를 한 번도 거치지 않았다(6/16 라이브는 매도·매수가
  4분 간격 별도 트리거였다). 이 스크립트로 '같은 사이클' 전환의 즉시성을 직접 관찰한다.

⚠️ 실제 모의 주문을 낸다:
  - trading_mode=real 이면 거부한다(실전 계좌에 검증 주문을 내지 않기 위해).
  - cron 트리거와 1~2분 텀을 둔다(KIS 토큰 분당 1회 제한 — HANDOFF '주의' 참고).
  - 현재 한 종목을 100% 보유한(정상 운용) 상태에서 실행해야 매도→매수가 관찰된다.

실행: python -m src.verify_switch
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from .config import get_settings
from .kis_client import build_kis_client
from .logging_setup import setup_logging
from .order_executor import ALL_TICKERS, TICKER, OrderExecutor
from .position_service import PositionService
from .state_store import StateStore
from .token_manager import TokenManager

logger = logging.getLogger(__name__)

SETTLE_WAIT = 3.0  # 매도 접수 후 체결·정산 반영을 기다리는 관찰 지연(초)


def _held_signal(holdings: dict) -> Optional[str]:
    """현재 보유 종목 → 신호(NASDAQ/GOLD). 보유 없음·혼재면 None(검증 불가)."""
    held = {s for s in ALL_TICKERS if int(holdings.get(s, 0) or 0) > 0}
    if held == {"QQQM"}:
        return "NASDAQ"
    if held == {"GLDM"}:
        return "GOLD"
    return None


def _report(tag: str, kis, positions: PositionService) -> dict:
    """보유·현금·총자산·종목별 매수여력을 한 줄로 출력하고 dict 로 반환."""
    snap = positions.snapshot()
    nav = snap.cash + positions.value_holdings(snap.holdings)
    buyable = {}
    for sym in ALL_TICKERS:
        px = kis.get_price(sym)
        buyable[sym] = kis.get_buyable_qty(sym, px) if px > 0 else 0
    print(f"[{tag}] 보유={snap.holdings or '없음(현금)'} 현금=${snap.cash:,.2f} 총자산=${nav:,.2f}")
    print("      매수여력: " + " / ".join(f"{s} {buyable[s]}주" for s in ALL_TICKERS))
    return {"holdings": dict(snap.holdings), "cash": snap.cash, "nav": nav}


def _target_weight(target: str, positions: PositionService) -> float:
    """전환 후 타겟 종목 평가비중(%) — 100%에 가까울수록 매도대금 정산이 즉시 반영된 것."""
    sym = TICKER.get(target)
    snap = positions.snapshot()
    nav = snap.cash + positions.value_holdings(snap.holdings)
    if not sym or nav <= 0:
        return 0.0
    held_val = positions.value_holdings({sym: int(snap.holdings.get(sym, 0) or 0)})
    return 100.0 * held_val / nav


def _switch(executor: OrderExecutor, kis, positions: PositionService, target: str) -> None:
    print(f"\n>>> execute('{target}') 트리거 — 매도→매수 (아래 KIS 호출 로그에서 "
          f"매도 ODNO·get_buyable_qty·매수 ODNO 를 확인)")
    executor.execute(target)
    _report(f"{target} 직후", kis, positions)
    print(f"    ⏳ {SETTLE_WAIT:.0f}초 대기(체결·정산 반영 관찰)...")
    time.sleep(SETTLE_WAIT)
    _report(f"{target} +{SETTLE_WAIT:.0f}s", kis, positions)
    w = _target_weight(target, positions)
    verdict = "정산 즉시 반영(정상)" if w >= 95 else "⚠️ 과소 매수 — 매도대금 미반영 의심"
    print(f"    진단: {TICKER[target]} 평가비중 {w:.1f}% → {verdict}")


def main() -> None:
    setup_logging()
    settings = get_settings()
    store = StateStore(settings.database_url)
    mode = store.get_trading_mode()
    if mode != "virtual":
        print(f"⛔ trading_mode={mode!r} — 검증은 모의(virtual)에서만 실행합니다. 중단.")
        return

    kis = build_kis_client(settings, "virtual")
    TokenManager(kis.issue_token).get_token()  # 사이클 1회 발급
    positions = PositionService(kis)
    executor = OrderExecutor(kis, positions, mode="virtual")

    print("=== 월말 전환 정산 타이밍 검증 (모의 전용) ===")
    init = _report("초기", kis, positions)
    orig = _held_signal(init["holdings"])
    if orig is None:
        print("\n현재 단일 종목 100% 보유가 아니라(현금 또는 혼재) 매도→매수 전환을 검증할 수 없습니다.")
        print("정상 운용 상태(한 종목 100% 보유)에서 다시 실행하세요.")
        return

    opposite = "GOLD" if orig == "NASDAQ" else "NASDAQ"
    print(f"\n현재 보유 신호={orig} → {opposite} 로 전환했다가 {orig} 로 원위치 복구합니다.")

    _switch(executor, kis, positions, opposite)   # A: 반대로 전환 — 매도→매수 정산 관찰
    _switch(executor, kis, positions, orig)        # B: 원위치 복구

    print("\n=== 요약 ===")
    _report("최종", kis, positions)
    print("두 전환의 '평가비중' 진단을 보세요. 95% 미만이 한 번이라도 나오면 매도대금이 같은")
    print("사이클 매수여력에 늦게 반영되는 것 → strategy_cycle 매수 전 정산 대기/재조회 보강 필요.")


if __name__ == "__main__":
    main()
