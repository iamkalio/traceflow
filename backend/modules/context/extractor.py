"""
Pull retrieval / RAG context from span metadata and Trace rows.

Used at ingest (metadata → JSONB ``context``) and at eval time (Trace → judge payload).
"""

from __future__ import annotations

import json
from typing import Any

from db.models import Trace

_CTX_META_KEYS = ("context", "rag_context", "retrieved_context", "retrieved_docs", "documents")


def extract_retrieval_from_metadata(metadata: dict[str, Any]) -> Any | None:
    """Best-effort raw retrieval payload from OTLP-style metadata (permissive while instrumentation evolves)."""
    for key in _CTX_META_KEYS:
        if key in metadata and metadata[key] not in (None, "", [], {}):
            return metadata[key]
    return None


def coerce_context_for_db(context: Any | None) -> Any | None:
    """Normalize context for Postgres JSONB (eval_runs.context, traces.context)."""
    if context is None:
        return None
    if isinstance(context, str):
        return {"text": context}
    try:
        json.dumps(context)
        return context
    except TypeError:
        return {"text": str(context)}


def _value_to_text(val: Any) -> str | None:
    if val is None or val == "" or val == [] or val == {}:
        return None
    if isinstance(val, str):
        s = val.strip()
        return s if s else None
    if isinstance(val, dict):
        if isinstance(val.get("text"), str) and val["text"].strip():
            return val["text"].strip()
        try:
            return json.dumps(val, ensure_ascii=False)
        except TypeError:
            return str(val)
    if isinstance(val, (list, tuple)):
        try:
            return json.dumps(val, ensure_ascii=False)
        except TypeError:
            return str(val)
    return str(val)


def extract_context_for_eval(row: Trace) -> str | None:
    """Flatten Trace.context column + metadata fallbacks into one string for judges."""
    if row.context is not None:
        t = _value_to_text(row.context)
        if t:
            return t
    attrs = row.attributes or {}
    meta = attrs.get("metadata")
    if not isinstance(meta, dict):
        return None
    for key in _CTX_META_KEYS:
        if key not in meta:
            continue
        t = _value_to_text(meta[key])
        if t:
            return t
    return None
