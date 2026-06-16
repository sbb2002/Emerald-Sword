"""CommandRouter — 조회/통제/모드/긴급정지 명령 검증."""
from src.commands import CommandDeps, CommandRouter, HELP_TEXT
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


def test_status_shows_holdings_cash_and_server(router):
    out = router.handle("/status", 42)
    assert "현재 상태" in out
    assert "QQQM 3주" in out
    assert "$125.50" in out
    assert "서버: 정상" in out


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
