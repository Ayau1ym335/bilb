"""
main.py  —  Uvicorn entrypoint
══════════════════════════════
Запуск:
  python main.py                         # разработка
  uvicorn main:app --host 0.0.0.0 --port 8000 --reload   # явно

▶ НАСТРОЙТЕ:
  HOST, PORT в .env или ниже
"""

import logging
import os

import uvicorn

logging.basicConfig(
    level=logging.DEBUG if os.getenv("DEBUG") else logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)

from ingestion.api import app   # noqa: E402 (импорт после logging setup)

HOST = os.getenv("API_HOST", "0.0.0.0")   # ▶ НАСТРОЙТЕ
PORT = int(os.getenv("API_PORT", "8000")) # ▶ НАСТРОЙТЕ

if __name__ == "__main__":
    uvicorn.run(
        "ingestion.api:app",
        host=HOST,
        port=PORT,
        reload=os.getenv("DEBUG", "false").lower() == "true",
        log_level="debug" if os.getenv("DEBUG") else "info",
    )
