"""표준 로깅 설정 — Render 로그(stdout)에 우리 모듈(`src.*`) 로그가 보이도록 구성한다.

uvicorn 은 자체 로거만 구성하므로 우리 `src.*` 로거는 기본 레벨(WARNING)이라 info 가 묻힌다.
'src' 부모 로거에 stdout 핸들러를 한 번만 붙이고 INFO 로 올려 가시성을 확보한다(중복 방지).
web(`web.py`)·cron(`cron.py`) 엔트리포인트에서 1회 호출한다.
"""
from __future__ import annotations

import logging
import sys

_CONFIGURED = False


def setup_logging(level: int = logging.INFO) -> None:
    global _CONFIGURED
    app_logger = logging.getLogger("src")
    app_logger.setLevel(level)
    if not _CONFIGURED:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        app_logger.addHandler(handler)
        app_logger.propagate = False  # 루트(uvicorn) 핸들러로의 중복 전파 방지
        _CONFIGURED = True
