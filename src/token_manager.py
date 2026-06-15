"""TokenManager — KIS 접근토큰 발급 빈도 제한 대응.

KIS: 접근토큰 24시간 유효, 발급 빈도 제한(1분당 1회).
→ 사이클당 1회 발급하고 그 사이클 내내 재사용한다. 폴백 재시도도 재발급 없이 재사용.
만료(안전 마진 포함) 시에만 재발급한다.
"""
from __future__ import annotations

import time
from typing import Callable, Optional

from .kis_interface import TokenInfo


class TokenManager:
    def __init__(
        self,
        issuer: Callable[[], TokenInfo],
        *,
        clock: Callable[[], float] = time.time,
        safety_margin_seconds: float = 300.0,
    ) -> None:
        self._issuer = issuer
        self._clock = clock
        self._margin = safety_margin_seconds
        self._token: Optional[TokenInfo] = None

    def get_token(self) -> str:
        now = self._clock()
        if self._token is None or now >= (self._token.expires_at - self._margin):
            self._token = self._issuer()
        return self._token.access_token

    def reset(self) -> None:
        """다음 사이클을 위해 캐시를 비운다(테스트·강제 재발급용)."""
        self._token = None
