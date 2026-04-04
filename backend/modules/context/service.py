"""Orchestration for context: compose extractor + future persistence."""

from __future__ import annotations

from typing import Any

from db.models import Trace
from modules.context.extractor import (
    coerce_context_for_db,
    extract_context_for_eval,
    extract_retrieval_from_metadata,
)
from modules.context.models import RetrievalSnapshot


def snapshot_from_span_metadata(metadata: dict[str, Any]) -> RetrievalSnapshot:
    raw = extract_retrieval_from_metadata(metadata)
    return RetrievalSnapshot(raw=raw, normalized_for_db=coerce_context_for_db(raw))


def text_for_eval(row: Trace) -> str | None:
    """Text block passed to LLM judges (same contract as ``extract_context_for_eval``)."""
    return extract_context_for_eval(row)
