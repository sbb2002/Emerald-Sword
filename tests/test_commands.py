"""CommandRouter — 조회 명령(#11: /status /signal /log) + /help 검증."""
from src.commands import HELP_TEXT
from src.state_store import TradeRecord


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
