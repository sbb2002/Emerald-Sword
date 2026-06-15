"""환경변수 로딩 — 모든 비밀값은 코드가 아니라 환경변수에서만 읽는다.

CLAUDE.md 절대 규칙 1: 비밀값(KIS 키, 텔레그램 토큰, DB URL)은 코드·git에 절대 넣지 않는다.
운영(Render)에서는 환경변수를 직접 주입하고, 로컬 개발에서는 .env(.gitignore 대상)를 쓴다.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

try:  # 로컬 개발 편의. 운영에는 .env 파일이 없어도 무방하다.
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # python-dotenv 미설치 등 — 무시하고 OS 환경변수만 사용
    pass


class ConfigError(RuntimeError):
    """필수 환경변수 누락 등 설정 오류."""


@dataclass(frozen=True)
class Settings:
    # 필수 (Phase A)
    database_url: str
    telegram_bot_token: str
    telegram_chat_id: int

    # KIS Open API (Phase B에서 사용 — Phase A 스켈레톤에서는 선택)
    kis_app_key: str | None = None
    kis_app_secret: str | None = None
    kis_cano_real: str | None = None
    kis_cano_paper: str | None = None
    kis_acnt_prdt_cd: str | None = None
    kis_base_url_real: str | None = None
    kis_base_url_paper: str | None = None


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ConfigError(f"필수 환경변수 누락: {name}")
    return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """환경변수에서 설정을 로딩한다(프로세스당 1회 캐시)."""
    chat_id_raw = _require("TELEGRAM_CHAT_ID")
    try:
        chat_id = int(chat_id_raw)
    except ValueError as exc:
        raise ConfigError("TELEGRAM_CHAT_ID 는 숫자여야 합니다.") from exc

    return Settings(
        database_url=_require("DATABASE_URL"),
        telegram_bot_token=_require("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=chat_id,
        kis_app_key=os.environ.get("KIS_APP_KEY"),
        kis_app_secret=os.environ.get("KIS_APP_SECRET"),
        kis_cano_real=os.environ.get("KIS_CANO_REAL"),
        kis_cano_paper=os.environ.get("KIS_CANO_PAPER"),
        kis_acnt_prdt_cd=os.environ.get("KIS_ACNT_PRDT_CD"),
        kis_base_url_real=os.environ.get("KIS_BASE_URL_REAL"),
        kis_base_url_paper=os.environ.get("KIS_BASE_URL_PAPER"),
    )
