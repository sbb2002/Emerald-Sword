"""CommandRouter — 조회/통제/모드/긴급정지 명령 검증."""
from src.commands import CommandDeps, CommandRouter, HELP_TEXT, StatusView
from src.mode_manager import ModeManager
from src.state_store import TradeRecord
from src.telegram_bot import TelegramBot

from tests.conftest import fake_signal, fake_status


def _router_with_code(store, code="135790"):
    """고정 챌린지 코드로 라우터를 만든다(/real·/emergency-stop 결정적 테스트용)."""
    return CommandRouter(CommandDeps(
        store=store,
        status_provider=fake_status,
        signal_provider=fake_signal,
        code_gen=lambda: code,
    ))


def _update(chat_id, text):
    return {"message": {"chat": {"id": chat_id}, "text": text}}


class FakeClock:
    """주입형 가짜 시계 — 비상정지 60초 타임아웃을 결정적으로 검증한다."""

    def __init__(self, t: float = 1000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t


def _estop_router(store, code="424242", clock=None, legs=None):
    """고정 코드·시계·청산결과로 비상정지 라우터를 만든다."""
    from src.order_executor import Leg, TransitionResult

    legs = legs if legs is not None else [Leg("SELL", "QQQM", 5, placed=True)]
    return CommandRouter(CommandDeps(
        store=store,
        status_provider=fake_status,
        signal_provider=fake_signal,
        code_gen=lambda: code,
        clock=clock or (lambda: 1000.0),
        liquidator=lambda: TransitionResult(
            target="CASH", target_symbol=None, legs=legs, complete=True
        ),
    ))


def test_help_lists_all_commands(router):
    out = router.handle("/help", 42)
    assert out == HELP_TEXT
    for cmd in ("/status", "/signal", "/log", "/pause", "/resume",
                "/virtual", "/real", "/emergency-stop", "/help"):
        assert cmd in out


def test_start_returns_help(router):
    assert router.handle("/start", 42) == HELP_TEXT


def test_unknown_command_falls_back_to_help(router):
    out = router.handle("/nope", 42)
    assert "알 수 없는 명령" in out
    assert HELP_TEXT in out


def test_status_shows_holdings_value_total_and_emoji(router):
    out = router.handle("/status", 42)
    assert "현재 상태" in out
    assert "QQQM 3주" in out
    assert "$1,455.00" in out        # 평가금액 3주 × $485
    assert "$125.50" in out          # 현금
    assert "총자산" in out
    assert "✅" in out               # 서버 상태 이모지
    assert "NASDAQ (QQQM)" in out    # 현재 신호


def test_status_shows_cash_in_krw_when_exrt_available(router):
    out = router.handle("/status", 42)
    assert "$125.50" in out          # USD 현금은 그대로 유지
    assert "₩173,190" in out         # 원화 병기 (125.50 × 1380, 정수 + 천단위 콤마)


def _status_router(store, **status_kwargs):
    """주어진 StatusView 필드로 /status 라우터를 만든다(환율 병기/폴백 검증용)."""
    base = dict(holdings={}, cash=1000.0, insufficient_for_next=False, server_ok=True)
    base.update(status_kwargs)
    sv = StatusView(**base)
    return CommandRouter(CommandDeps(store=store, status_provider=lambda: sv))


def test_status_falls_back_to_usd_only_when_exrt_missing(store):
    out = _status_router(store, exrt=None).handle("/status", 42)
    assert "$1,000.00" in out
    assert "₩" not in out            # 환율 없으면 USD만 (폴백)


def test_status_falls_back_to_usd_only_when_exrt_zero(store):
    # get_exrt 실패 시 0.0 을 돌려주므로 0 도 폴백 처리돼야 한다.
    out = _status_router(store, exrt=0.0).handle("/status", 42)
    assert "$1,000.00" in out
    assert "₩" not in out


def test_signal_previews_current_target(router):
    out = router.handle("/signal", 42)
    assert "NASDAQ (QQQM)" in out
    assert "+12.00%" in out  # score_nasdaq 0.12
    assert "+5.00%" in out   # score_gold 0.05


def test_log_empty(router, store):
    store.trades = []
    assert "거래 내역이 없습니다" in router.handle("/log", 42)


def test_log_all_latest_first(router, store):
    store.trades = [
        TradeRecord("2026-06-30 00:10", "real", "GOLD", "BUY", "GLDM", 2, "monthly_signal"),
        TradeRecord("2026-05-31 00:10", "real", "NASDAQ", "BUY", "QQQM", 3, "monthly_signal"),
    ]
    out = router.handle("/log", 42)
    assert out.index("GLDM") < out.index("QQQM")  # 최신순(최근 거래가 먼저)


def test_log_n_limits_count(router, store):
    store.trades = [
        TradeRecord(f"2026-0{i}-28 00:00", "real", "NASDAQ", "BUY", "QQQM", i, "monthly_signal")
        for i in range(1, 6)
    ]
    out = router.handle("/log 3", 42)
    assert out.count("QQQM") == 3


def test_log_rejects_non_integer(router):
    assert "사용법" in router.handle("/log abc", 42)


def test_emergency_stop_trade_is_marked_in_log(router, store):
    store.trades = [
        TradeRecord("2026-06-16 12:00", "real", "CASH", "SELL", "QQQM", 5, "emergency_stop"),
    ]
    out = router.handle("/log", 42)
    assert "비상청산" in out


def test_log_shows_fill_price_and_balance_change(router, store):
    store.trades = [
        TradeRecord("2026-06-30 00:10", "real", "GOLD", "BUY", "GLDM", 2, "monthly_signal",
                    fill_price=61.25, balance_before=1000.0, balance_after=877.5),
    ]
    out = router.handle("/log", 42)
    assert "@ $61.25" in out                # 체결가
    assert "$1,000.00→$877.50" in out       # 잔고 변화(전→후)


def test_log_shows_nav_and_cash_when_present(router, store):
    # 총자산(NAV)과 현금을 함께 표시 — 원화 자동환전으로 현금만 보면 어긋나 보이던 혼란 해소.
    store.trades = [
        TradeRecord("2026-06-30 00:10", "real", "NASDAQ", "BUY", "QQQM", 324, "monthly_signal",
                    fill_price=300.56, balance_before=99382.95, balance_after=998.50,
                    nav_before=99382.95, nav_after=98379.94),
    ]
    out = router.handle("/log", 42)
    assert "총자산 $99,382.95→$98,379.94" in out
    assert "현금 $99,382.95→$998.50" in out
    assert "잔고" not in out                 # 옛 라벨은 더 이상 쓰지 않음


def test_log_omits_fill_price_and_balance_when_none(router, store):
    store.trades = [
        TradeRecord("2026-05-31 00:10", "real", "NASDAQ", "BUY", "QQQM", 3, "monthly_signal"),
    ]
    out = router.handle("/log", 42)
    assert "@" not in out          # 체결가 None → 생략
    assert "잔고" not in out        # 잔고 None → 생략
    assert "QQQM 3주" in out        # 기존 줄 포맷은 유지
    assert "[NASDAQ]" in out


def test_record_trade_persists_order_price_to_log(router, store):
    # place_order 의 지정가(order.price)가 record_trade → fill_price → /log 로 흐른다(저장 경로).
    from src.kis_interface import OrderResult
    from src.order_executor import Leg
    leg = Leg("BUY", "QQQM", 3, placed=True,
              order=OrderResult(order_id="o1", symbol="QQQM", side="BUY",
                                quantity=3, accepted=True, price=300.0))
    store.record_trade(mode="virtual", signal="NASDAQ", legs=[leg],
                       balance_before=1000.0, balance_after=100.0)
    out = router.handle("/log", 42)
    assert "@ $300.00" in out


# ----- 통제 명령 (#12) -----

def test_pause_asks_confirmation_then_pauses(router, store):
    out1 = router.handle("/pause", 42)
    assert "(y/n)" in out1
    assert store.is_paused() is False  # 확인 전에는 갱신되지 않는다
    out2 = router.handle("y", 42)
    assert store.is_paused() is True
    assert "일시정지" in out2


def test_pause_cancelled_on_no(router, store):
    router.handle("/pause", 42)
    out = router.handle("n", 42)
    assert store.is_paused() is False
    assert "취소" in out


def test_pause_when_already_paused_no_pending(router, store):
    store.set_paused(True)
    out = router.handle("/pause", 42)
    assert "이미 일시정지" in out
    # 펜딩이 생기지 않아야 한다 — 다음 임의 입력은 일반 명령으로 처리
    assert "알 수 없는 명령" in router.handle("blah", 42)


def test_resume_clears_pause(router, store):
    store.set_paused(True)
    out = router.handle("/resume", 42)
    assert store.is_paused() is False
    assert "재개" in out


def test_resume_when_already_running(router, store):
    out = router.handle("/resume", 42)
    assert "이미 작동" in out


def test_new_command_during_pending_aborts_confirmation(router, store):
    router.handle("/pause", 42)             # pause_confirm 펜딩
    out = router.handle("/status", 42)      # 새 /명령 → 펜딩 폐기 + status 실행
    assert "현재 상태" in out
    assert store.is_paused() is False
    # 펜딩이 폐기됐으므로 이후 "y" 는 일반 명령(미지)으로 처리
    assert "알 수 없는 명령" in router.handle("y", 42)


# ----- 모드 전환 (#13) -----

def test_virtual_confirm_switches_mode(store):
    store.set_trading_mode("real")
    r = _router_with_code(store)
    assert "(y/n)" in r.handle("/virtual", 42)
    out = r.handle("y", 42)
    assert store.get_trading_mode() == "virtual"
    assert "모의투자" in out


def test_virtual_when_already_virtual(store):
    r = _router_with_code(store)            # 기본 virtual
    assert "이미 모의투자" in r.handle("/virtual", 42)


def test_real_switches_on_correct_code(store):
    store.set_trading_mode("virtual")
    r = _router_with_code(store, code="246813")
    out1 = r.handle("/real", 42)
    assert "246813" in out1
    assert "실제 자금" in out1
    out2 = r.handle("246813", 42)
    assert store.get_trading_mode() == "real"
    assert "실전" in out2


def test_real_rejects_wrong_code(store):
    store.set_trading_mode("virtual")
    r = _router_with_code(store, code="246813")
    r.handle("/real", 42)
    out = r.handle("000000", 42)
    assert store.get_trading_mode() == "virtual"  # 변경 없음
    assert "일치하지 않" in out


def test_real_when_already_real(store):
    store.set_trading_mode("real")
    r = _router_with_code(store)
    assert "이미 실전" in r.handle("/real", 42)


def test_mode_tag_reflects_switch_immediately(store, sender):
    store.set_trading_mode("virtual")
    r = _router_with_code(store, code="111111")
    bot = TelegramBot(42, ModeManager(store), sender, store=store, router=r)
    bot.handle_update(_update(42, "/real"))
    bot.handle_update(_update(42, "111111"))
    # 전환 확인 메시지부터 [실전] 태그로 발신돼야 한다(모드 우선 갱신)
    assert sender.sent[-1][1].startswith("[실전]")
    assert store.get_trading_mode() == "real"


# ----- 비상 정지 (#14) -----

def test_emergency_stop_full_flow_liquidates_and_pauses(store):
    store.set_trading_mode("real")
    r = _estop_router(store, code="424242")
    out1 = r.handle("/emergency-stop", 42)
    assert "(y/n)" in out1
    out2 = r.handle("y", 42)
    assert "424242" in out2 and "60초" in out2
    out3 = r.handle("424242", 42)
    assert store.is_paused() is True                       # 청산 후 자동 pause
    assert "청산 완료" in out3
    assert any(t.reason == "emergency_stop" for t in store.read_trades(None))  # /log 기록


def test_emergency_stop_cancelled_on_first_no(store):
    r = _estop_router(store)
    r.handle("/emergency-stop", 42)
    out = r.handle("n", 42)
    assert "취소" in out
    assert store.is_paused() is False


def test_emergency_stop_wrong_code_aborts(store):
    r = _estop_router(store, code="424242")
    r.handle("/emergency-stop", 42)
    r.handle("y", 42)
    out = r.handle("000000", 42)
    assert "일치하지 않" in out
    assert store.is_paused() is False          # 코드 불일치 → pause·청산 모두 없음
    assert store.read_trades(None) == []


def test_emergency_stop_timeout_cancels_even_with_correct_code(store):
    clock = FakeClock(1000.0)
    r = _estop_router(store, code="424242", clock=clock)
    r.handle("/emergency-stop", 42)
    r.handle("y", 42)                           # expires_at = 1000 + 60 = 1060
    clock.t = 1061.0                            # 60초 초과
    out = r.handle("424242", 42)                # 정확한 코드라도 만료면 거부
    assert "초과" in out
    assert store.is_paused() is False
    assert store.read_trades(None) == []


def test_emergency_stop_within_timeout_executes(store):
    clock = FakeClock(1000.0)
    r = _estop_router(store, code="424242", clock=clock)
    r.handle("/emergency-stop", 42)
    r.handle("y", 42)
    clock.t = 1059.0                            # 60초 이내
    out = r.handle("424242", 42)
    assert "청산 완료" in out
    assert store.is_paused() is True


# ----- 예외 가드(외부 호출 실패가 webhook 을 500 내지 않게) -----

def _boom():
    raise RuntimeError("KIS down")


def test_handler_catches_provider_error_returns_friendly(store):
    r = CommandRouter(CommandDeps(store=store, status_provider=_boom, signal_provider=_boom))
    assert "오류가 발생" in r.handle("/status", 42)   # 가드 없으면 raise
    assert "오류가 발생" in r.handle("/signal", 42)


# ----- 입출금 기록 (/deposit·/withdraw) -----

def test_deposit_records_cash_flow_after_confirm(store):
    r = CommandRouter(CommandDeps(store=store, nav_provider=lambda: 100000.0))
    out1 = r.handle("/deposit 5000", 42)
    assert "입금" in out1 and "$5,000.00" in out1 and "100,000" in out1
    assert "기록 완료" in r.handle("y", 42)
    assert len(store.cash_flows) == 1
    cf = store.cash_flows[0]
    assert cf["amount"] == 5000.0
    assert cf["direction"] == "deposit"
    assert cf["nav_before"] == 100000.0       # 입금 직전 NAV 가 기록됨(TWR 구간 분할용)
    assert cf["mode"] == "virtual"


def test_withdraw_records_with_direction(store):
    r = CommandRouter(CommandDeps(store=store, nav_provider=lambda: 100000.0))
    r.handle("/withdraw 3000", 42)
    assert "기록 완료" in r.handle("y", 42)
    assert store.cash_flows[0]["direction"] == "withdraw"
    assert store.cash_flows[0]["amount"] == 3000.0


def test_deposit_cancelled_on_no(store):
    r = CommandRouter(CommandDeps(store=store, nav_provider=lambda: 100000.0))
    r.handle("/deposit 5000", 42)
    assert "취소" in r.handle("n", 42)
    assert store.cash_flows == []


def test_withdraw_exceeding_nav_rejected(store):
    r = CommandRouter(CommandDeps(store=store, nav_provider=lambda: 1000.0))
    assert "보다 큽니다" in r.handle("/withdraw 5000", 42)
    assert store.cash_flows == []             # 확인 단계로 가지 않음


def test_deposit_invalid_amount(store):
    r = CommandRouter(CommandDeps(store=store, nav_provider=lambda: 100000.0))
    assert "숫자" in r.handle("/deposit abc", 42)
    assert "사용법" in r.handle("/deposit", 42)
    assert store.cash_flows == []


# ----- /status 수익률 표시 -----

def test_status_shows_twr_pnl_and_cagr_notice(store):
    def sv():
        return StatusView(
            holdings={"QQQM": 324}, cash=998.50, insufficient_for_next=False,
            server_ok=True, prices={"QQQM": 300.56}, signal="NASDAQ", exrt=1380.0,
            holding_pnl={"QQQM": -1.65}, twr=-0.0162, cagr=None, running_days=92,
        )
    out = CommandRouter(CommandDeps(store=store, status_provider=sv)).handle("/status", 42)
    assert "-1.65%" in out                     # 보유 평가손익률 병기
    assert "수익률(TWR): -1.62%" in out         # TWR
    assert "운용 3개월" in out                  # 1년 미만 → CAGR 숨김 안내 (92//30)


def test_status_shows_cagr_when_one_year_passed(store):
    def sv():
        return StatusView(
            holdings={}, cash=110000.0, insufficient_for_next=False, server_ok=True,
            twr=0.21, cagr=0.10, running_days=800,
        )
    out = CommandRouter(CommandDeps(store=store, status_provider=sv)).handle("/status", 42)
    assert "CAGR: +10.00%" in out


def test_status_omits_returns_when_absent(store):
    # twr=None(예: cash_flows 없음)이면 수익률·CAGR 줄을 아예 표시하지 않는다.
    out = CommandRouter(CommandDeps(store=store, status_provider=fake_status)).handle("/status", 42)
    assert "TWR" not in out and "CAGR" not in out


def test_bot_replies_friendly_and_does_not_raise_on_error(store, sender):
    r = CommandRouter(CommandDeps(store=store, signal_provider=_boom))
    bot = TelegramBot(42, ModeManager(store), sender, store=store, router=r)
    handled = bot.handle_update(_update(42, "/signal"))  # 예외가 전파되면 테스트가 깨진다
    assert handled is True
    assert sender.sent[-1][1].startswith("[모의]")        # 모드 태그 유지
    assert "오류가 발생" in sender.sent[-1][1]
