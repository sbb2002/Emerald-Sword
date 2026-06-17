"""영속 상태 저장소 (Neon PostgreSQL).

Phase A 범위: is_paused, trading_mode 읽기/쓰기.
거래 로그·승인·신호 테이블은 마이그레이션으로 생성만 해두고 Phase B/C에서 사용한다.
포지션은 저장하지 않는다(PositionService가 실시간 조회 — CLAUDE.md).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .db import get_connection

VALID_MODES = ("virtual", "real")


@dataclass(frozen=True)
class TradeRecord:
    """trade_log 한 행의 읽기 전용 뷰(/log 표시용)."""

    executed_at: str            # "YYYY-MM-DD HH:MM"
    mode: str                   # virtual | real
    signal: Optional[str]       # NASDAQ | GOLD | CASH
    side: Optional[str]         # BUY | SELL
    ticker: Optional[str]       # QQQM | GLDM
    quantity: Optional[int]
    reason: Optional[str]       # monthly_signal | emergency_stop | ...


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

    # ----- webhook 멱등성 (processed_updates) -----
    def claim_update(self, update_id: int) -> bool:
        """처음 보는 update_id 면 기록하고 True, 이미 처리한 것이면 False 를 반환한다.

        Telegram 은 webhook 응답이 느리면(특히 Render free-tier cold-start) 같은 update 를
        재전송한다. 이 claim 으로 재전송분을 가려내 같은 명령이 두 번 실행·두 번 응답되는 것을 막는다.
        INSERT ... ON CONFLICT DO NOTHING 이라 동시 재시도까지 원자적으로 1회만 통과시킨다.
        """
        with get_connection(self._database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO processed_updates (update_id) VALUES (%s)"
                    " ON CONFLICT (update_id) DO NOTHING;",
                    (update_id,),
                )
                return cur.rowcount == 1

    # ----- 마지막 신호 (last_signal) -----
    def get_last_signal(self) -> Optional[str]:
        with get_connection(self._database_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT signal FROM last_signal WHERE id = 1;")
                row = cur.fetchone()
        return row[0] if row and row[0] else None

    def set_last_signal(self, signal: str, score_nasdaq: float, score_gold: float) -> None:
        with get_connection(self._database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE last_signal SET signal=%s, score_nasdaq=%s, score_gold=%s, computed_at=now()"
                    " WHERE id = 1;",
                    (signal, score_nasdaq, score_gold),
                )

    # ----- 거래 로그 (trade_log) -----
    def record_trade(
        self,
        *,
        mode: str,
        signal: str,
        legs,
        balance_before=None,
        balance_after=None,
        reason: str = "monthly_signal",
    ) -> None:
        with get_connection(self._database_url) as conn:
            with conn.cursor() as cur:
                for leg in legs:
                    if not getattr(leg, "placed", False):
                        continue
                    cur.execute(
                        "INSERT INTO trade_log"
                        " (mode, signal, side, ticker, quantity, reason, balance_before, balance_after)"
                        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s);",
                        (mode, signal, leg.side, leg.symbol, leg.quantity, reason, balance_before, balance_after),
                    )

    def read_trades(self, limit: Optional[int] = None) -> list:
        """거래 로그를 최신순으로 읽는다. limit=None 이면 전체(/log [N])."""
        sql = (
            "SELECT executed_at, mode, signal, side, ticker, quantity, reason"
            " FROM trade_log ORDER BY executed_at DESC, id DESC"
        )
        params: tuple = ()
        if limit is not None:
            sql += " LIMIT %s"
            params = (limit,)
        with get_connection(self._database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(sql + ";", params)
                rows = cur.fetchall()
        out: list = []
        for r in rows:
            ts = r[0]
            ts = ts.isoformat(sep=" ", timespec="minutes") if hasattr(ts, "isoformat") else str(ts)
            out.append(TradeRecord(ts, r[1], r[2], r[3], r[4], int(r[5]) if r[5] is not None else None, r[6]))
        return out
