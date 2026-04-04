"""HTTP / job payloads for context features."""

from __future__ import annotations
from typing import Any

from pydantic import BaseModel, Field


class ContextExtractOut(BaseModel):
    """Diagnostic view of extracted retrieval (e.g. for debugging ingest)."""

    had_payload: bool
    char_count: int = 0
    keys_seen: list[str] = Field(default_factory=list)
