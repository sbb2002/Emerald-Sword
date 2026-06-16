"""텔레그램 Bot API HTTP 클라이언트.

외부 의존(HTTP)을 이 좁은 클래스로 격리해, 테스트에서는 mock 으로 대체한다
(CLAUDE.md 테스트 방침: KIS·텔레그램·DB는 인터페이스로 추상화해 mock 으로 대체).
"""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class TelegramClient:
    def __init__(self, bot_token: str, timeout: float = 10.0) -> None:
        self._base = f"https://api.telegram.org/bot{bot_token}"
        self._timeout = timeout

    def send_message(self, chat_id: int, text: str) -> None:
        try:
            resp = httpx.post(
                f"{self._base}/sendMessage",
                json={"chat_id": chat_id, "text": text},
                timeout=self._timeout,
            )
        except Exception:
            logger.exception("텔레그램 sendMessage 요청 실패: chat_id=%s", chat_id)
            raise
        if resp.status_code != 200:
            # 예: {"ok":false,"description":"Forbidden: bot was blocked by the user"} / "chat not found"
            logger.error("텔레그램 sendMessage 비정상 응답 %s: %s", resp.status_code, resp.text)
        resp.raise_for_status()
