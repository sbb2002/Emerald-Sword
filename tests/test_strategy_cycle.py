"""전략 사이클 오케스트레이터 — mock 환경 통합 테스트 (이슈 #8)."""
from src.kis_interface import OrderResult
from src.mode_manager import ModeManager
from src.order_executor import Leg, TransitionResult
from src.strategy_cycle import (
    EXECUTED,
    INCOMPLETE,
    OUTLIER_PENDING,
    PAUSED,
    UNCHANGED,
    CycleDeps,
    run_cycle,
)
from src.telegram_bot import TelegramBot

NASDAQ_RISING = list(range(100, 113))      # 13개, 상승
GOLD_FALLING = list(range(200, 187, -1))   # 13개, 하락 → 신호 NASDAQ


class FakeStore:
    def __init__(self, paused=False, last_signal=None, mode="virtual"):
        self._paused = paused
        self._last = last_signal
        self._mode = mode
        self.saved_signal = None
        self.trades = []

    def is_paused(self):
        return self._paused

    def get_trading_mode(self):
        return self._mode

    def get_last_signal(self):
        return self._last

    def set_last_signal(self, target, sn, sg):
        self.saved_signal = (target, sn, sg)

    def record_trade(self, **kw):
        self.trades.append(kw)


class _MD:
    def __init__(self, closes, outliers):
        self.month_end_closes = closes
        self.outliers = outliers


class FakeMarket:
    def __init__(self, nasdaq, gold, out_n=None, out_g=None):
        self._n, self._g = nasdaq, gold
        self._on, self._og = out_n or [], out_g or []

    def get(self, symbol, months):
        if symbol == "QQQM":
            return _MD(self._n, self._on)
        return _MD(self._g, self._og)


class Pos:
    def __init__(self, holdings, cash):
        self.holdings, self.cash = holdings, cash


class FakePositions:
    def __init__(self, snapshots):
        self._snaps = list(snapshots)
        self._i = 0

    def snapshot(self):
        s = self._snaps[min(self._i, len(self._snaps) - 1)]
        self._i += 1
        return s


class FakeExecutor:
    def __init__(self, transition):
        self._t = transition
        self.calls = 0

    def execute(self, target):
        self.calls += 1
        return self._t


class _Settle:
    def __init__(self, complete):
        self.complete = complete


class FakeFill:
    def __init__(self, complete=True):
        self._c = complete

    def settle(self, transition):
        return _Settle(self._c)


class FakeFallback:
    def __init__(self):
        self.incomplete_calls = 0

    def on_incomplete_fill(self, *a, **k):
        self.incomplete_calls += 1


class FakeToken:
    def __init__(self):
        self.calls = 0

    def get_token(self):
        self.calls += 1
        return "tok"


class FakeSender:
    def __init__(self):
        self.sent = []

    def send_message(self, chat_id, text):
        self.sent.append((chat_id, text))


def _transition():
    sell = Leg("SELL", "GLDM", 4, placed=True, order=OrderResult("o1", "GLDM", "SELL", 4, True))
    buy = Leg("BUY", "QQQM", 3, placed=True, order=OrderResult("o2", "QQQM", "BUY", 3, True))
    return TransitionResult("NASDAQ", "QQQM", [sell, buy], True)


def _build(store, *, market=None, fill_complete=True, positions=None):
    sender = FakeSender()
    bot = TelegramBot(42, ModeManager(store), sender)
    fakes = {
        "sender": sender,
        "executor": FakeExecutor(_transition()),
        "fallback": FakeFallback(),
        "token": FakeToken(),
        "store": store,
    }
    deps = CycleDeps(
        store=store,
        notify=bot.send_message,
        token_manager=fakes["token"],
        market_data=market or FakeMarket(NASDAQ_RISING, GOLD_FALLING),
        positions=positions or FakePositions([Pos({"GLDM": 4}, 1000.0), Pos({"QQQM": 3}, 50.0)]),
        order_executor=fakes["executor"],
        fill_handler=FakeFill(fill_complete),
        fallback=fakes["fallback"],
    )
    return deps, fakes


def test_paused_skips_and_notifies():
    deps, f = _build(FakeStore(paused=True))
    result = run_cycle(deps)
    assert result.status == PAUSED
    assert f["executor"].calls == 0
    assert f["token"].calls == 0
    assert "일시정지" in f["sender"].sent[-1][1]


def test_executes_and_reports_with_mode_tag_and_details():
    deps, f = _build(FakeStore(last_signal=None))
    result = run_cycle(deps)
    assert result.status == EXECUTED
    assert result.target == "NASDAQ"
    assert f["executor"].calls == 1
    assert f["store"].saved_signal[0] == "NASDAQ"
    assert len(f["store"].trades) == 1
    msg = f["sender"].sent[-1][1]
    assert msg.startswith("[모의]")               # 모드 태그
    assert "매도: GLDM 4주" in msg                  # 매도 내역
    assert "매수: QQQM 3주" in msg                  # 매수 내역
    assert "잔고: $1000.0 → $50.0" in msg           # 잔고 변화


def test_partial_fill_reported_honestly():
    # 324주 매수가 접수(rt_cd=0)됐어도 실보유가 77주만 늘었으면 '부분체결'로 정직하게 보고.
    deps, f = _build(
        FakeStore(last_signal=None),
        positions=FakePositions([Pos({}, 100000.0), Pos({"QQQM": 77}, 1000.0)]),
    )
    f["executor"]._t = TransitionResult(
        "NASDAQ", "QQQM",
        [Leg("BUY", "QQQM", 324, placed=True, order=OrderResult("o1", "QQQM", "BUY", 324, True))],
        complete=True,
    )
    result = run_cycle(deps)
    assert result.status == EXECUTED
    msg = f["sender"].sent[-1][1]
    assert "⚠️" in msg                     # 완료(✅)로 위장하지 않음
    assert "77/324주 체결" in msg
    assert "247주 미체결" in msg
    assert "미체결분" in msg                # 장중 대기/만료 안내


def test_full_fill_marked_complete():
    # 주문 수량만큼 실보유가 늘면 완전체결(✅) 로 보고.
    deps, f = _build(
        FakeStore(last_signal=None),
        positions=FakePositions([Pos({}, 100000.0), Pos({"QQQM": 324}, 1000.0)]),
    )
    f["executor"]._t = TransitionResult(
        "NASDAQ", "QQQM",
        [Leg("BUY", "QQQM", 324, placed=True, order=OrderResult("o1", "QQQM", "BUY", 324, True))],
        complete=True,
    )
    result = run_cycle(deps)
    assert result.status == EXECUTED
    msg = f["sender"].sent[-1][1]
    assert "324주 체결 ✅" in msg
    assert "미체결" not in msg
    assert "전환 완료" in msg


def test_already_holding_target_no_trade():
    # 실제로 목표(QQQM)를 이미 보유하면 무거래 — 직전 신호 값과 무관.
    deps, f = _build(FakeStore(), positions=FakePositions([Pos({"QQQM": 3}, 50.0)]))
    result = run_cycle(deps)
    assert result.status == UNCHANGED
    assert f["executor"].calls == 0
    assert "무거래" in f["sender"].sent[-1][1]


def test_stale_last_signal_does_not_block_empty_position():
    # 자가치유: 직전 신호=NASDAQ(실패한 사이클 잔재)라도 실보유가 없으면 매수 실행.
    deps, f = _build(
        FakeStore(last_signal="NASDAQ"),
        positions=FakePositions([Pos({}, 1000.0), Pos({"QQQM": 3}, 50.0)]),
    )
    result = run_cycle(deps)
    assert result.status == EXECUTED
    assert f["executor"].calls == 1


def test_outlier_holds_without_trading():
    market = FakeMarket(NASDAQ_RISING, GOLD_FALLING, out_n=["2025-06-15"])
    deps, f = _build(FakeStore(), market=market)
    result = run_cycle(deps)
    assert result.status == OUTLIER_PENDING
    assert f["executor"].calls == 0
    assert "이상치" in f["sender"].sent[-1][1]


def test_incomplete_fill_triggers_fallback():
    deps, f = _build(FakeStore(last_signal=None), fill_complete=False)
    result = run_cycle(deps)
    assert result.status == INCOMPLETE
    assert f["fallback"].incomplete_calls == 1


def test_insufficient_cash_not_reported_as_completed():
    # 현금 부족으로 낸 주문이 0건이면 '전환 완료'가 아니라 '잔고 부족'으로 보고.
    deps, f = _build(FakeStore(), positions=FakePositions([Pos({}, 0.0)]))
    f["executor"]._t = TransitionResult(
        "NASDAQ", "QQQM",
        [Leg("BUY", "QQQM", 0, placed=False, skipped_reason="insufficient_cash")],
        complete=True,
    )
    result = run_cycle(deps)
    assert result.status == INCOMPLETE
    msg = f["sender"].sent[-1][1]
    assert "현금" in msg and "부족" in msg
