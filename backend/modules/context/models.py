"""Domain types for trace / RAG context (expand with persisted context entities later)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RetrievalSnapshot:
    """In-memory view of what was retrieved for a span (not necessarily ORM-backed yet)."""

    raw: Any | None
    normalized_for_db: Any | None
    text_preview: str | None = None
