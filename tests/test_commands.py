"""commands.dispatch — /help 및 미구현 명령 안내 검증."""
from src.commands import HELP_TEXT, dispatch


def test_help_lists_all_commands():
    out = dispatch("/help")
    assert out == HELP_TEXT
    for cmd in (
        "/status",
        "/signal",
        "/log",
        "/pause",
        "/resume",
        "/virtual",
        "/real",
        "/emergency-stop",
        "/help",
    ):
        assert cmd in out


def test_start_returns_help():
    assert dispatch("/start") == HELP_TEXT


def test_known_command_is_coming_soon():
    assert "곧 제공" in dispatch("/status")
    assert "곧 제공" in dispatch("/log 5")  # 인자가 있어도 첫 토큰으로 인식


def test_unknown_command_falls_back_to_help():
    out = dispatch("/nope")
    assert "알 수 없는 명령" in out
    assert HELP_TEXT in out
