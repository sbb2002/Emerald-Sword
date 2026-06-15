"""ModeManager — 발신 메시지 모드 태그 단일 주입점 검증."""
from src.mode_manager import ModeManager, TAG_REAL, TAG_VIRTUAL


def test_virtual_tag_prepended(store):
    store.set_trading_mode("virtual")
    mm = ModeManager(store)
    assert mm.mode_tag() == TAG_VIRTUAL
    assert mm.decorate("안녕").startswith(TAG_VIRTUAL)


def test_real_tag_prepended(store):
    store.set_trading_mode("real")
    mm = ModeManager(store)
    out = mm.decorate("주문 완료")
    assert out.startswith(TAG_REAL)
    assert "주문 완료" in out


def test_mode_tag_follows_current_state(store):
    mm = ModeManager(store)
    store.set_trading_mode("virtual")
    assert mm.decorate("x").startswith(TAG_VIRTUAL)
    store.set_trading_mode("real")
    assert mm.decorate("x").startswith(TAG_REAL)
