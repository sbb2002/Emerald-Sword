"""모드(모의/실전) 상태 + 발신 메시지 모드 태그의 단일 주입점.

PRD: 모든 발신 메시지 머리에 현재 모드 태그([모의]/[실전])를 붙인다.
decorate() 가 바로 그 "단일 지점"이다 — 발신은 반드시 이 메서드를 거친다.
"""
from __future__ import annotations

from typing import Protocol

TAG_REAL = "[실전]"
TAG_VIRTUAL = "[모의]"


class ModeSource(Protocol):
    def get_trading_mode(self) -> str: ...


class ModeManager:
    def __init__(self, source: ModeSource) -> None:
        self._source = source

    def current_mode(self) -> str:
        return self._source.get_trading_mode()

    def mode_tag(self) -> str:
        return TAG_REAL if self.current_mode() == "real" else TAG_VIRTUAL

    def decorate(self, message: str) -> str:
        return f"{self.mode_tag()} {message}"
