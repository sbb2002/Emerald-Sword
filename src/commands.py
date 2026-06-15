"""텔레그램 명령 디스패처.

Phase A 범위: /help(과 /start)만 실제 동작한다.
나머지 명령은 등록만 해두고 "곧 제공" 안내를 돌려준다.
(조회 #11 · 통제 #12 · 모드 #13 · 긴급정지 #14 는 Phase C 이슈에서 구현)
"""
from __future__ import annotations

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

_COMING_SOON = {
    "/status",
    "/signal",
    "/log",
    "/pause",
    "/resume",
    "/virtual",
    "/real",
    "/emergency-stop",
    "/emergency_stop",
}


def dispatch(text: str) -> str:
    """명령 텍스트를 받아 응답 문자열을 돌려준다(부수효과 없음 — 발신은 TelegramBot 담당)."""
    stripped = text.strip()
    cmd = stripped.split()[0].lower() if stripped else ""
    if cmd in ("/help", "/start"):
        return HELP_TEXT
    if cmd in _COMING_SOON:
        return f"'{cmd}' 명령은 곧 제공됩니다. 지금은 /help 로 명령어를 확인하세요."
    return f"알 수 없는 명령입니다: {text!r}\n\n{HELP_TEXT}"
