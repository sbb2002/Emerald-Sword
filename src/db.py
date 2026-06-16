"""psycopg3 기반 PostgreSQL(Neon) 커넥션 헬퍼.

월 1회 + 명령 응답이라는 저빈도 운영이므로 연결 풀 없이 작업 단위로 단기 커넥션을 연다.
정상 종료 시 commit, 예외 시 rollback 후 항상 close.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator


@contextmanager
def get_connection(database_url: str) -> Iterator["psycopg.Connection"]:
    import psycopg  # 지연 import — state_store/TradeRecord 를 psycopg 없이 import 가능하게(테스트 격리)

    conn = psycopg.connect(database_url)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
