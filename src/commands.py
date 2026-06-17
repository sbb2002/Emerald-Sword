"""텔레그램 명령 라우터 — 상태머신 + 의존성 주입 (Phase C).

Phase A 의 무상태 dispatch() 를 CommandRouter 로 대체한다.
- 조회(#11): /status /signal /log — 주입된 provider 로 KIS·DB 를 읽어 즉시 응답.
- 통제(#12)·모드(#13)·긴급정지(#14): 다중턴 확인/챌린지 흐름(이후 커밋에서 추가).

격리 규칙: 이 모듈은 httpx/psycopg 를 import 하지 않는다. provider 콜러블을
주입받아 mock 으로 테스트한다(엔트리포인트 web.py 가 실제 KIS·DB 를 배선).
발신 메시지의 모드 태그([모의]/[실전])는 TelegramBot.send_message 가 단일 지점에서
주입하므로 여기서는 붙이지 않는다.
"""
from __future__ import annotations

import logging
import secrets
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

HELP_TEXT = (
    "복합모멘텀 QQQM/GLDM 봇 — 명령어\n"
    "/status — 보유·잔고·서버 상태\n"
    "/signal — 현재 기준 예상 신호 미리보기\n"
    "/log [N] — 최근 N개(또는 전체) 거래 내역\n"
    "/pause — 자동거래 일시정지\n"
    "/resume — 자동거래 재개\n"
    "/virtual — 모의투자 모드 전환\n"
    "/real — 실전 모드 전환 (확인코드 필요)\n"
    "/emergency-stop — 전량 청산 후 중지\n"
    "/help — 이 도움말"
)
# /deposit·/withdraw 는 의도적으로 HELP 에 넣지 않은 '숨은 명령'이다(아래 _command 참고).


@dataclass
class StatusView:
    """/status 가 표시할 데이터(포맷은 라우터가 담당 — 테스트가 포맷을 검증)."""

    holdings: dict                       # {symbol: quantity}
    cash: float
    insufficient_for_next: bool
    server_ok: bool
    prices: Optional[dict] = None        # {symbol: 현재가} — 평가금액 계산용(없으면 금액 생략)
    signal: Optional[str] = None         # 현재 모멘텀 신호(NASDAQ|GOLD|CASH), best-effort
    exrt: Optional[float] = None         # 원·달러 환율(KRW/USD) — 현금 원화 병기용. 없거나 0이면 USD만
    holding_pnl: Optional[dict] = None   # {symbol: 평가손익률(%)} — 보유 줄에 병기(KIS evlu_pfls_rt)
    twr: Optional[float] = None          # 계좌 누적 수익률(시간가중, 입출금 보정). 0.0123 = +1.23%
    cagr: Optional[float] = None         # TWR 연율화(운용 1년 이상일 때만, 아니면 None)
    running_days: Optional[int] = None   # 운용 경과 일수 — CAGR 숨김 시 '운용 N개월' 안내


def _default_code() -> str:
    """6자리 확인 코드(실전 전환·비상정지 챌린지용). 추측 방지를 위해 secrets 사용."""
    return f"{secrets.randbelow(900_000) + 100_000}"


@dataclass
class CommandDeps:
    store: Any                                            # is_paused/set_paused/get·set_trading_mode/read_trades/record_trade/get_last_signal
    status_provider: Optional[Callable[[], StatusView]] = None
    signal_provider: Optional[Callable[[], Any]] = None   # -> SignalResult(target, score_nasdaq, score_gold)
    liquidator: Optional[Callable[[], Any]] = None        # -> TransitionResult(legs)  (OrderExecutor.execute("CASH"))
    code_gen: Callable[[], str] = _default_code           # 챌린지 코드 생성(테스트는 고정값 주입)
    clock: Callable[[], float] = time.time                # 비상정지 60초 타임아웃 판정(테스트는 가짜 시계 주입)
    nav_provider: Optional[Callable[[], float]] = None    # 현재 총자산(USD) — /deposit·/withdraw nav_before 기록용


def _fmt_money(value: float) -> str:
    try:
        return f"${value:,.2f}"
    except (TypeError, ValueError):
        return f"${value}"


def _fmt_krw(value: float) -> str:
    """원화 표시 — 정수 + 천단위 콤마(예: ₩151,000,000). 소수점 없음."""
    try:
        return f"₩{value:,.0f}"
    except (TypeError, ValueError):
        return f"₩{value}"


def _fmt_cash(cash: float, exrt: Optional[float]) -> str:
    """현금 USD 표시. 환율이 있으면 원화 병기(예: $100,000.00 (₩151,000,000)).
    환율이 없거나 0이면 USD만 표시(폴백)."""
    usd = _fmt_money(cash)
    if exrt and exrt > 0:
        return f"{usd} ({_fmt_krw(cash * exrt)})"
    return usd


def _fmt_ratio(rate: Optional[float]) -> str:
    """비율(0.0123)을 부호 붙은 퍼센트(+1.23%)로. None 이면 '—'. (TWR/CAGR 용)"""
    if rate is None:
        return "—"
    return f"{rate * 100.0:+.2f}%"


def _fmt_pct_value(pct: Optional[float]) -> str:
    """이미 퍼센트값(1.23)을 부호 붙여(+1.23%). None 이면 '—'. (KIS evlu_pfls_rt 용)"""
    if pct is None:
        return "—"
    return f"{pct:+.2f}%"


def _is_yes(text: str) -> bool:
    return text.strip().lower() in ("y", "yes")


@dataclass
class _Pending:
    """진행 중인 다중턴 대화(확인/챌린지). chat_id 별로 1건 보관(인메모리)."""

    kind: str                       # pause_confirm | virtual_confirm | real_challenge | estop_confirm | estop_challenge | deposit_confirm | withdraw_confirm
    code: Optional[str] = None      # 챌린지 코드(real/estop)
    expires_at: Optional[float] = None  # 만료 시각(estop 60초)
    amount: Optional[float] = None      # 입출금액 USD (deposit/withdraw 확인)
    nav_before: Optional[float] = None  # 입출금 직전 총자산 USD (deposit/withdraw 기록용)


class CommandRouter:
    """텔레그램 명령을 받아 응답 문자열을 돌려준다(발신은 TelegramBot 담당)."""

    def __init__(self, deps: CommandDeps) -> None:
        self._deps = deps
        self._pending: dict[int, _Pending] = {}

    def handle(self, text: str, chat_id: int) -> str:
        stripped = (text or "").strip()
        # 펜딩은 1회성으로 꺼낸다(있으면 소비/폐기). 비-/명령이면 펜딩 응답으로, 그 외엔 새 명령으로.
        pending = self._pending.pop(chat_id, None)
        try:
            if pending is not None and not stripped.startswith("/"):
                return self._answer_pending(pending, stripped, chat_id)
            return self._command(stripped, chat_id)
        except Exception:
            # KIS/네트워크 등 외부 호출 실패가 webhook 을 500 내지 않도록 흡수한다.
            # 사용자에겐 친절히 안내하고, 원인 스택은 서버 로그(Render)로 남긴다.
            logger.exception("명령 처리 실패 (chat_id=%s)", chat_id)
            return (
                "⚠️ 명령 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.\n"
                "계속되면 KIS 연결·키 설정을 확인하세요. (/status 로 서버 상태 확인)"
            )

    def _answer_pending(self, pending: _Pending, text: str, chat_id: int) -> str:
        if pending.kind == "pause_confirm":
            return self._on_pause_confirm(text)
        if pending.kind == "virtual_confirm":
            return self._on_virtual_confirm(text)
        if pending.kind == "real_challenge":
            return self._on_real_challenge(pending, text)
        if pending.kind == "estop_confirm":
            return self._on_estop_confirm(text, chat_id)
        if pending.kind == "estop_challenge":
            return self._on_estop_challenge(pending, text)
        if pending.kind in ("deposit_confirm", "withdraw_confirm"):
            return self._on_cashflow_confirm(pending, text)
        return self._command(text, chat_id)  # 알 수 없는 펜딩 — 안전 폴백

    # ----- 명령 디스패치 -----
    def _command(self, text: str, chat_id: int) -> str:
        cmd = text.split()[0].lower() if text else ""
        if cmd in ("/help", "/start"):
            return HELP_TEXT
        if cmd == "/status":
            return self._status()
        if cmd == "/signal":
            return self._signal()
        if cmd == "/log":
            return self._log(text)
        if cmd == "/pause":
            return self._pause(chat_id)
        if cmd == "/resume":
            return self._resume()
        if cmd == "/virtual":
            return self._virtual(chat_id)
        if cmd == "/real":
            return self._real(chat_id)
        if cmd in ("/emergency-stop", "/emergency_stop"):
            return self._emergency_stop(chat_id)
        # /deposit·/withdraw 는 HELP 미노출 '숨은 명령' — 입출금 기록(수익률 TWR 기준점).
        # 실전 전환 후 자금을 추가할 때만 쓰므로 평상시 도움말에서 제외(동작은 정상).
        if cmd == "/deposit":
            return self._cashflow("deposit", text, chat_id)
        if cmd == "/withdraw":
            return self._cashflow("withdraw", text, chat_id)
        return f"알 수 없는 명령입니다: {text!r}\n\n{HELP_TEXT}"

    # ----- 조회 (#11) -----
    def _status(self) -> str:
        sv = self._deps.status_provider()
        prices = sv.prices or {}
        lines = ["📊 현재 상태"]
        holdings_value = 0.0
        pnl = sv.holding_pnl or {}
        if sv.holdings:
            for sym, qty in sv.holdings.items():
                px = prices.get(sym, 0.0)
                pnl_str = f", {_fmt_pct_value(pnl[sym])}" if pnl.get(sym) is not None else ""
                if px > 0:
                    val = qty * px
                    holdings_value += val
                    lines.append(f"  보유: {sym} {qty}주 (~{_fmt_money(val)}{pnl_str})")
                else:
                    lines.append(f"  보유: {sym} {qty}주{f' ({_fmt_pct_value(pnl[sym])})' if pnl.get(sym) is not None else ''}")
        else:
            lines.append("  보유: 없음 (현금)")
        lines.append(f"  현금: {_fmt_cash(sv.cash, sv.exrt)}")
        lines.append(f"  총자산: ~{_fmt_money(holdings_value + sv.cash)}")
        if sv.twr is not None:
            lines.append(f"  수익률(TWR): {_fmt_ratio(sv.twr)}")
            if sv.cagr is not None:
                lines.append(f"  CAGR: {_fmt_ratio(sv.cagr)}")
            elif sv.running_days is not None:
                lines.append(f"  CAGR: 운용 {sv.running_days // 30}개월 (1년 경과 후 표시)")
        if sv.signal:
            label = {
                "NASDAQ": "NASDAQ (QQQM)",
                "GOLD": "GOLD (GLDM)",
                "CASH": "CASH (현금)",
            }.get(sv.signal, sv.signal)
            lines.append(f"  신호: {label}")
        lines.append(f"  다음 거래 잔고부족: {'예' if sv.insufficient_for_next else '아니오'}")
        lines.append(f"  서버: {'✅ 정상' if sv.server_ok else '⚠️ 오류'}")
        return "\n".join(lines)

    def _signal(self) -> str:
        sig = self._deps.signal_provider()
        label = {
            "NASDAQ": "NASDAQ (QQQM)",
            "GOLD": "GOLD (GLDM)",
            "CASH": "CASH (현금)",
        }.get(sig.target, sig.target)
        return (
            f"🔭 현재 기준 예상 신호: {label}\n"
            f"  NASDAQ 점수: {sig.score_nasdaq:+.2%}\n"
            f"  GOLD 점수: {sig.score_gold:+.2%}"
        )

    def _log(self, text: str) -> str:
        parts = text.split()
        limit: Optional[int] = None
        if len(parts) > 1:
            try:
                limit = int(parts[1])
            except ValueError:
                return "사용법: /log 또는 /log N (N은 정수)"
            if limit <= 0:
                return "N은 1 이상의 정수여야 합니다."
        trades = self._deps.store.read_trades(limit)
        if not trades:
            return "거래 내역이 없습니다."
        header = f"📒 거래 내역 (최근 {len(trades)}건)" if limit else f"📒 거래 내역 (전체 {len(trades)}건)"
        lines = [header]
        for t in trades:
            verb = "매도" if t.side == "SELL" else "매수"
            mark = " ⚠️비상청산" if t.reason == "emergency_stop" else ""
            fill_price = getattr(t, "fill_price", None)
            price_str = f" @ {_fmt_money(fill_price)}" if fill_price is not None else ""
            bb = getattr(t, "balance_before", None)
            ba = getattr(t, "balance_after", None)
            bal_str = (
                f" · 잔고 {_fmt_money(bb)}→{_fmt_money(ba)}"
                if bb is not None and ba is not None else ""
            )
            lines.append(
                f"  {t.executed_at} · {verb} {t.ticker} {t.quantity}주{price_str}"
                f" [{t.signal}]{mark}{bal_str}"
            )
        return "\n".join(lines)

    # ----- 통제 (#12) -----
    def _pause(self, chat_id: int) -> str:
        if self._deps.store.is_paused():
            return "이미 일시정지 상태입니다."
        self._pending[chat_id] = _Pending(kind="pause_confirm")
        return (
            "현재 진행 중인 거래가 있다면 취소되고 일시정지됩니다.\n"
            "일시정지할까요? (y/n)"
        )

    def _on_pause_confirm(self, text: str) -> str:
        if not _is_yes(text):
            return "일시정지를 취소했습니다."
        # is_paused=True 만 갱신 — 실제 '거래 중단'은 cron 이 기상 시 이 플래그를 보고
        # 사이클 전체를 건너뛰어 실현한다(KIS 에 주문 취소 API 가 없음).
        self._deps.store.set_paused(True)
        return "⏸️ 자동거래를 일시정지했습니다. (다음 월말 사이클을 건너뜁니다)"

    def _resume(self) -> str:
        if not self._deps.store.is_paused():
            return "이미 작동 중입니다."
        self._deps.store.set_paused(False)
        return "▶️ 자동거래를 재개했습니다."

    # ----- 입출금 기록 (수익률 TWR 의 기준) -----
    def _cashflow(self, direction: str, text: str, chat_id: int) -> str:
        verb = "입금" if direction == "deposit" else "출금"
        parts = text.split()
        if len(parts) < 2:
            return f"사용법: /{direction} 금액(USD)  예: /{direction} 5000"
        try:
            amount = float(parts[1].replace(",", "").lstrip("$"))
        except ValueError:
            return f"금액은 숫자여야 합니다. 예: /{direction} 5000"
        if amount <= 0:
            return "금액은 0보다 커야 합니다."
        nav = self._deps.nav_provider() if self._deps.nav_provider else None
        if nav is None:
            return "현재 총자산을 조회할 수 없어 기록을 보류합니다. 잠시 후 다시 시도하세요."
        if direction == "withdraw" and amount > nav:
            return f"출금액({_fmt_money(amount)})이 현재 총자산({_fmt_money(nav)})보다 큽니다. 확인 후 다시 시도하세요."
        self._pending[chat_id] = _Pending(kind=f"{direction}_confirm", amount=amount, nav_before=nav)
        return (
            f"{verb} {_fmt_money(amount)} 을(를) 기록할까요? (현재 총자산 {_fmt_money(nav)} 기준)\n"
            "※ 실제 송금이 아니라 수익률 계산용 기록입니다. (y/n)"
        )

    def _on_cashflow_confirm(self, pending: _Pending, text: str) -> str:
        direction = "deposit" if pending.kind == "deposit_confirm" else "withdraw"
        verb = "입금" if direction == "deposit" else "출금"
        if not _is_yes(text):
            return f"{verb} 기록을 취소했습니다."
        self._deps.store.record_cash_flow(
            mode=self._deps.store.get_trading_mode(),
            amount=pending.amount,
            direction=direction,
            nav_before=pending.nav_before,
        )
        return f"✅ {verb} {_fmt_money(pending.amount)} 기록 완료. 수익률(TWR) 계산에 반영됩니다."

    # ----- 모드 전환 (#13) -----
    def _virtual(self, chat_id: int) -> str:
        if self._deps.store.get_trading_mode() == "virtual":
            return "이미 모의투자 모드입니다."
        self._pending[chat_id] = _Pending(kind="virtual_confirm")
        return "모의투자 모드로 전환할까요? (y/n)"

    def _on_virtual_confirm(self, text: str) -> str:
        if not _is_yes(text):
            return "모드 전환을 취소했습니다."
        self._deps.store.set_trading_mode("virtual")
        return "🧪 모의투자 모드로 전환했습니다."

    def _real(self, chat_id: int) -> str:
        if self._deps.store.get_trading_mode() == "real":
            return "이미 실전 모드입니다."
        code = self._deps.code_gen()
        self._pending[chat_id] = _Pending(kind="real_challenge", code=code)
        return (
            "⚠️ 실전 계좌로 전환합니다. 실제 자금이 거래됩니다.\n"
            f"   확인하려면 다음 코드를 그대로 입력하세요: {code}"
        )

    def _on_real_challenge(self, pending: _Pending, text: str) -> str:
        if text.strip() != pending.code:
            return "코드가 일치하지 않습니다. 실전 전환을 취소했습니다. (모드 변경 없음)"
        # 모드를 먼저 갱신 → 이 확인 메시지부터 send_message 가 [실전] 태그로 발신.
        self._deps.store.set_trading_mode("real")
        return "🔴 실전 모드로 전환했습니다. 실제 자금이 거래됩니다."

    # ----- 비상 정지 (#14) -----
    def _emergency_stop(self, chat_id: int) -> str:
        self._pending[chat_id] = _Pending(kind="estop_confirm")
        return "🚨 전량 청산됩니다. 정말 진행할까요? (y/n)"

    def _on_estop_confirm(self, text: str, chat_id: int) -> str:
        if not _is_yes(text):
            return "비상정지를 취소했습니다."
        code = self._deps.code_gen()
        self._pending[chat_id] = _Pending(
            kind="estop_challenge", code=code, expires_at=self._deps.clock() + 60,
        )
        return (
            "⚠️ 최종 확인 — 전량 청산을 실행합니다. 60초 안에 아래 코드를 그대로 입력하세요.\n"
            f"   확인 코드: {code}"
        )

    def _on_estop_challenge(self, pending: _Pending, text: str) -> str:
        # 1) 60초 타임아웃(무응답·지연 시 자동 취소 — 정확한 코드라도 만료면 거부)
        if pending.expires_at is not None and self._deps.clock() > pending.expires_at:
            return "⏱️ 시간이 초과되어 청산이 취소되었습니다."
        # 2) 코드 검증 — 불일치면 청산·pause 모두 일어나지 않는다
        if text.strip() != pending.code:
            return "코드가 일치하지 않습니다. 청산이 취소되었습니다."
        # 3) early-pause 안전장치: 청산 주문 '전에' 먼저 pause 한다.
        #    청산 도중 프로세스가 죽어도 '일시정지 + 일부청산'이라는 안전한 실패 모드가 되어
        #    다음 월말 재매수가 차단된다(User Story 38). execute("CASH") 는 멱등이라 재실행으로 마무리 가능.
        self._deps.store.set_paused(True)
        try:
            transition = self._deps.liquidator()
        except Exception:
            return (
                "⚠️ 청산 주문 중 오류가 발생했습니다. 자동거래는 일시정지된 상태입니다.\n"
                "/status 로 실제 잔고를 확인하고 필요하면 /emergency-stop 을 다시 실행하세요."
            )
        # 4) 거래 로그에 별도 사유로 기록(/log 에서 ⚠️비상청산 으로 표시)
        self._deps.store.record_trade(
            mode=self._deps.store.get_trading_mode(),
            signal="CASH",
            legs=transition.legs,
            reason="emergency_stop",
        )
        return self._format_liquidation(transition)

    @staticmethod
    def _format_liquidation(transition: Any) -> str:
        lines = ["🚨 비상 청산 완료 — 자동거래를 일시정지했습니다."]
        placed = [leg for leg in transition.legs if getattr(leg, "placed", False)]
        if placed:
            for leg in placed:
                lines.append(f"  매도: {leg.symbol} {leg.quantity}주 (접수)")
        else:
            lines.append("  (청산할 보유 종목이 없었습니다)")
        lines.append("  다음 월말 재매수를 막기 위해 일시정지 상태입니다. /resume 으로 재개할 수 있습니다.")
        return "\n".join(lines)
