"""
llm/rag.py  —  Retrieval-Augmented Generation
═══════════════════════════════════════════════
Простой RAG без внешних векторных БД.
Для MVP: загружает все .md/.txt из knowledge_base/ в память,
  индексирует по TF-IDF, возвращает топ-K релевантных чанков.

Для продакшна: заменить _build_index() на ChromaDB/FAISS.
Интерфейс (retrieve()) остаётся тем же.

▶ НАСТРОЙТЕ:
  KNOWLEDGE_BASE_DIR  — путь к папке с документами
  CHUNK_SIZE          — размер чанка в токенах (~слова)
  TOP_K               — сколько чанков возвращать
"""

from __future__ import annotations

import logging
import math
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Optional

log = logging.getLogger("bilb.rag")

# ── Настройки ─────────────────────────────────────────────────
KNOWLEDGE_BASE_DIR = Path(
    os.getenv("KB_DIR", Path(__file__).parent / "knowledge_base")
)
CHUNK_SIZE  = int(os.getenv("RAG_CHUNK_SIZE", "150"))   # слов ▶ НАСТРОЙТЕ
TOP_K       = int(os.getenv("RAG_TOP_K",     "4"))      # чанков ▶ НАСТРОЙТЕ
MAX_CONTEXT = int(os.getenv("RAG_MAX_TOKENS", "3000"))  # символов в итоговом контексте


# ══════════════════════════════════════════════════════════════
#  Чанкинг документа
# ══════════════════════════════════════════════════════════════
def _chunk_text(text: str, source: str) -> list[dict]:
    """
    Разбивает текст на чанки по CHUNK_SIZE слов с перекрытием 20%.
    Каждый чанк: {"text": str, "source": str, "chunk_id": int}
    """
    words  = text.split()
    step   = max(1, int(CHUNK_SIZE * 0.8))   # 20% перекрытие
    chunks = []
    for i, start in enumerate(range(0, len(words), step)):
        chunk_words = words[start : start + CHUNK_SIZE]
        if len(chunk_words) < 10:            # слишком короткий → пропуск
            continue
        chunks.append({
            "text":     " ".join(chunk_words),
            "source":   source,
            "chunk_id": i,
        })
    return chunks


# ══════════════════════════════════════════════════════════════
#  TF-IDF индекс (in-memory)
# ══════════════════════════════════════════════════════════════
def _tokenize(text: str) -> list[str]:
    """Нижний регистр + только буквы/цифры."""
    return re.findall(r"[a-zA-Zа-яА-Я0-9]+", text.lower())


class _TFIDFIndex:
    """Простой TF-IDF без внешних зависимостей."""

    def __init__(self, chunks: list[dict]) -> None:
        self.chunks = chunks
        self.N      = len(chunks)

        # Обратный индекс: term → {chunk_id: tf}
        self._inv: dict[str, dict[int, float]] = defaultdict(dict)
        # IDF: term → float
        self._idf: dict[str, float] = {}

        for cid, chunk in enumerate(chunks):
            tokens = _tokenize(chunk["text"])
            if not tokens:
                continue
            tf_raw: dict[str, int] = defaultdict(int)
            for t in tokens:
                tf_raw[t] += 1
            for t, cnt in tf_raw.items():
                self._inv[t][cid] = cnt / len(tokens)

        for term, postings in self._inv.items():
            df = len(postings)
            self._idf[term] = math.log((self.N + 1) / (df + 1)) + 1.0

    def query(self, text: str, k: int = TOP_K) -> list[dict]:
        """Возвращает топ-k чанков по TF-IDF косинусному сходству."""
        q_tokens  = _tokenize(text)
        scores    = defaultdict(float)
        q_weights = defaultdict(float)

        for t in q_tokens:
            if t not in self._idf:
                continue
            w = self._idf[t]
            q_weights[t] = w
            for cid, tf in self._inv[t].items():
                scores[cid] += tf * w

        if not scores:
            return []

        # L2 нормализация вектора запроса
        q_norm = math.sqrt(sum(v * v for v in q_weights.values())) or 1.0

        ranked = sorted(scores.items(), key=lambda x: x[1] / q_norm, reverse=True)
        return [self.chunks[cid] for cid, _ in ranked[:k]]


# ══════════════════════════════════════════════════════════════
#  Загрузка knowledge base
# ══════════════════════════════════════════════════════════════
_index: Optional[_TFIDFIndex] = None


def _ensure_kb_dir() -> None:
    """Создаёт пустую KB директорию если не существует."""
    KNOWLEDGE_BASE_DIR.mkdir(parents=True, exist_ok=True)


def _load_index() -> _TFIDFIndex:
    global _index
    if _index is not None:
        return _index

    _ensure_kb_dir()
    all_chunks: list[dict] = []

    for ext in ("*.md", "*.txt"):
        for fpath in sorted(KNOWLEDGE_BASE_DIR.glob(ext)):
            try:
                text   = fpath.read_text(encoding="utf-8", errors="replace")
                chunks = _chunk_text(text, fpath.name)
                all_chunks.extend(chunks)
                log.debug("KB: loaded %s → %d chunks", fpath.name, len(chunks))
            except Exception as e:
                log.warning("KB: failed to load %s: %s", fpath.name, e)

    if not all_chunks:
        log.warning("KB: knowledge_base/ is empty — RAG will have no context")

    log.info("KB: indexed %d chunks from %d files", len(all_chunks),
             len(list(KNOWLEDGE_BASE_DIR.glob("*.md"))) +
             len(list(KNOWLEDGE_BASE_DIR.glob("*.txt"))))

    _index = _TFIDFIndex(all_chunks)
    return _index


def reload_index() -> None:
    """Перезагружает индекс — вызывать после добавления новых KB-файлов."""
    global _index
    _index = None
    _load_index()


# ══════════════════════════════════════════════════════════════
#  Публичный API
# ══════════════════════════════════════════════════════════════
def retrieve(query: str, k: int = TOP_K) -> str:
    """
    Возвращает релевантный контекст из knowledge base как одну строку.
    Готов к вставке в промпт Gemini.

    query — свободный текст запроса (проблемы здания, тип сценария, ...)
    k     — количество чанков
    """
    idx    = _load_index()
    chunks = idx.query(query, k=k)

    if not chunks:
        return ""

    parts = []
    total = 0
    for chunk in chunks:
        header = f"[{chunk['source']}]"
        body   = chunk["text"]
        piece  = f"{header}\n{body}"
        if total + len(piece) > MAX_CONTEXT:
            break
        parts.append(piece)
        total += len(piece) + 1

    return "\n\n".join(parts)


def list_kb_files() -> list[str]:
    """Список загруженных файлов knowledge base."""
    _ensure_kb_dir()
    return [f.name for f in sorted(KNOWLEDGE_BASE_DIR.glob("*.md"))] + \
           [f.name for f in sorted(KNOWLEDGE_BASE_DIR.glob("*.txt"))]
