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

from dataclasses import dataclass
from typing import Any, Callable, Optional

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


@dataclass
class StatusView:
    """/status 가 표시할 데이터(포맷은 라우터가 담당 — 테스트가 포맷을 검증)."""

    holdings: dict           # {symbol: quantity}
    cash: float
    insufficient_for_next: bool
    server_ok: bool


@dataclass
class CommandDeps:
    store: Any                                            # is_paused/set_paused/get·set_trading_mode/read_trades/record_trade/get_last_signal
    status_provider: Optional[Callable[[], StatusView]] = None
    signal_provider: Optional[Callable[[], Any]] = None   # -> SignalResult(target, score_nasdaq, score_gold)


def _fmt_money(value: float) -> str:
    try:
        return f"${value:,.2f}"
    except (TypeError, ValueError):
        return f"${value}"


class CommandRouter:
    """텔레그램 명령을 받아 응답 문자열을 돌려준다(발신은 TelegramBot 담당)."""

    def __init__(self, deps: CommandDeps) -> None:
        self._deps = deps

    def handle(self, text: str, chat_id: int) -> str:
        return self._command((text or "").strip(), chat_id)

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
        return f"알 수 없는 명령입니다: {text!r}\n\n{HELP_TEXT}"

    # ----- 조회 (#11) -----
    def _status(self) -> str:
        sv = self._deps.status_provider()
        lines = ["📊 현재 상태"]
        if sv.holdings:
            for sym, qty in sv.holdings.items():
                lines.append(f"  보유: {sym} {qty}주")
        else:
            lines.append("  보유: 없음 (현금)")
        lines.append(f"  현금: {_fmt_money(sv.cash)}")
        lines.append(f"  다음 거래 잔고부족: {'예' if sv.insufficient_for_next else '아니오'}")
        lines.append(f"  서버: {'정상' if sv.server_ok else '오류'}")
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
            lines.append(f"  {t.executed_at} · {verb} {t.ticker} {t.quantity}주 [{t.signal}]{mark}")
        return "\n".join(lines)
