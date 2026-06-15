"""영속 상태 저장소 (Neon PostgreSQL).

Phase A 범위: is_paused, trading_mode 읽기/쓰기.
거래 로그·승인·신호 테이블은 마이그레이션으로 생성만 해두고 Phase B/C에서 사용한다.
포지션은 저장하지 않는다(PositionService가 실시간 조회 — CLAUDE.md).
"""
from __future__ import annotations

from .db import get_connection

VALID_MODES = ("virtual", "real")


class StateStore:
    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def is_paused(self) -> bool:
        with get_connection(self._database_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT is_paused FROM bot_state WHERE id = 1;")
                row = cur.fetchone()
        return bool(row[0]) if row else False

    def set_paused(self, paused: bool) -> None:
        with get_connection(self._database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE bot_state SET is_paused = %s, updated_at = now() WHERE id = 1;",
                    (paused,),
                )

    def get_trading_mode(self) -> str:
        with get_connection(self._database_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT trading_mode FROM bot_state WHERE id = 1;")
                row = cur.fetchone()
        return row[0] if row else "virtual"

    def set_trading_mode(self, mode: str) -> None:
        if mode not in VALID_MODES:
            raise ValueError(f"잘못된 trading_mode: {mode!r} (허용: {VALID_MODES})")
        with get_connection(self._database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE bot_state SET trading_mode = %s, updated_at = now() WHERE id = 1;",
                    (mode,),
                )
