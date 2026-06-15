"""SQL 마이그레이션 러너.

src/migrations/*.sql 를 파일명 순으로 적용한다. 적용 이력을 schema_migrations 테이블에
기록하므로 몇 번을 재실행해도 멱등하다.

호출 지점:
  - web: 서버 startup(lifespan)에서 자동 실행
  - cron: 사이클 시작 시 스키마 보장
  - 수동/배포: `python -m src.migrate`
"""
from __future__ import annotations

from pathlib import Path

import psycopg

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

_ENSURE_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def _applied_versions(conn: "psycopg.Connection") -> set[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT version FROM schema_migrations;")
        return {row[0] for row in cur.fetchall()}


def run_migrations(database_url: str) -> list[str]:
    """미적용 마이그레이션을 순서대로 적용하고, 이번에 적용한 버전 목록을 반환."""
    applied_now: list[str] = []
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))

    conn = psycopg.connect(database_url)
    try:
        with conn.cursor() as cur:
            cur.execute(_ENSURE_TABLE)
        conn.commit()

        done = _applied_versions(conn)
        for path in files:
            version = path.name
            if version in done:
                continue
            sql = path.read_text(encoding="utf-8")
            with conn.cursor() as cur:
                cur.execute(sql)  # 파라미터 없는 다중 문장 — psycopg3 허용
                cur.execute(
                    "INSERT INTO schema_migrations (version) VALUES (%s);",
                    (version,),
                )
            conn.commit()
            applied_now.append(version)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return applied_now


def main() -> None:
    from .config import get_settings

    settings = get_settings()
    applied = run_migrations(settings.database_url)
    if applied:
        print(f"적용된 마이그레이션: {', '.join(applied)}")
    else:
        print("새로 적용할 마이그레이션 없음 (최신 상태).")


if __name__ == "__main__":
    main()
