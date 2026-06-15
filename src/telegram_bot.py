"""텔레그램 봇 오케스트레이션: 인증 게이트 + 발신(모드 태그 주입) + 명령 라우팅.

- 인증 게이트: 등록된 chat_id 외 메시지는 무시 (PRD User Story 34).
- 발신: send_message() 가 ModeManager.decorate() 를 거쳐 모드 태그를 단일 지점에서 주입.

TelegramSender 는 구조적 인터페이스(Protocol)다. 운영에서는 TelegramClient,
테스트에서는 가짜 sender 가 이 자리를 채운다(httpx 의존 없이 봇 로직만 검증 가능).
"""
from __future__ import annotations

from typing import Any, Optional, Protocol

from .commands import dispatch
from .mode_manager import ModeManager


class TelegramSender(Protocol):
    def send_message(self, chat_id: int, text: str) -> None: ...


class TelegramBot:
    def __init__(
        self,
        allowed_chat_id: int,
        mode_manager: ModeManager,
        sender: TelegramSender,
        store: Any = None,
    ) -> None:
        self._allowed_chat_id = allowed_chat_id
        self._mode = mode_manager
        self._sender = sender
        self._store = store

    def is_authorized(self, chat_id: Optional[int]) -> bool:
        return chat_id is not None and chat_id == self._allowed_chat_id

    def send_message(self, text: str, chat_id: Optional[int] = None) -> None:
        target = chat_id if chat_id is not None else self._allowed_chat_id
        self._sender.send_message(target, self._mode.decorate(text))

    @staticmethod
    def extract(update: dict) -> tuple[Optional[int], str]:
        message = update.get("message") or update.get("edited_message") or {}
        chat_id = (message.get("chat") or {}).get("id")
        text = message.get("text") or ""
        return chat_id, text

    def handle_update(self, update: dict) -> bool:
        """webhook update 처리. 인증 통과 시 명령을 처리·응답하고 True, 아니면 False(무시)."""
        chat_id, text = self.extract(update)
        if not self.is_authorized(chat_id):
            return False  # 미등록 chat_id 무시
        reply = dispatch(text)
        self.send_message(reply, chat_id=chat_id)
        return True
