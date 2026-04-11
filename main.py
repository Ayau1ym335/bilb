"""
main.py  —  Uvicorn entrypoint
══════════════════════════════
Запуск:
  python main.py                         # разработка
  uvicorn main:app --host 0.0.0.0 --port 8000 --reload   # явно

▶ НАСТРОЙТЕ в .env или окружении:
  DEBUG=1          — подробные логи (root + uvicorn log_level)
  RELOAD=1         — uvicorn --reload (только разработка; не включайте в проде)
  API_HOST, API_PORT
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import uvicorn
from dotenv import load_dotenv

# Load .env before any os.getenv used for process behaviour (also done in database.py).
load_dotenv()


def _env_truthy(name: str, default: str = "false") -> bool:
    """True for 1, true, yes, on (case-insensitive); empty uses default."""
    raw = os.getenv(name)
    if raw is None:
        raw = default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_str(name: str, default: str) -> str:
    """Like getenv with default, but empty/whitespace-only → default."""
    raw = os.getenv(name)
    if raw is None:
        return default
    s = raw.strip()
    return s if s else default


def _parse_port(raw: Optional[str], default: int = 8000) -> int:
    if raw is None:
        return default
    s = raw.strip()
    if not s:
        return default
    port = int(s)
    if not 1 <= port <= 65535:
        raise ValueError(f"API_PORT must be 1–65535, got {port}")
    return port


_DEBUG = _env_truthy("DEBUG", "false")

logging.basicConfig(
    level=logging.DEBUG if _DEBUG else logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
    force=True,
)

from ingestion.api import APP_IMPORT_NAME, app  # noqa: E402 (после logging setup)

HOST = _env_str("API_HOST", "127.0.0.1")  # ▶ НАСТРОЙТЕ
PORT = _parse_port(os.getenv("API_PORT"), 8000)  # ▶ НАСТРОЙТЕ

if __name__ == "__main__":
    # Re-read so `python main.py` matches env even if something toggled os.environ
    # after import (tests); logging level may still reflect import-time DEBUG.
    debug = _env_truthy("DEBUG", "false")
    reload_on = _env_truthy("RELOAD", "false")
    target: str | object = APP_IMPORT_NAME if reload_on else app
    uvicorn.run(
        target,
        host=HOST,
        port=PORT,
        reload=reload_on,
        log_level="debug" if debug else "info",
    )
