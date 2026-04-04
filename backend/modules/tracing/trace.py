"""W3C-style trace id helpers for in-app request correlation (distinct from OTLP ingest trace ids)."""

from __future__ import annotations

import secrets


def generate_request_trace_id() -> str:
    """32 lowercase hex chars (16 bytes), suitable for ``traceparent``-style headers."""
    return secrets.token_hex(16)


def normalize_traceparent_trace_id(header_value: str | None) -> str | None:
    """
    Parse ``trace_id`` from W3C ``traceparent`` (``00-{trace_id}-{span_id}-01``).

    Returns None if missing or malformed.
    """
    if not header_value:
        return None
    parts = header_value.strip().split("-")
    if len(parts) < 2:
        return None
    tid = parts[1].strip().lower()
    if len(tid) == 32 and all(c in "0123456789abcdef" for c in tid):
        return tid
    return None


def ensure_trace_id(existing: str | None, traceparent_header: str | None) -> str:
    """Prefer incoming traceparent; else reuse ``existing``; else mint a new id."""
    from_tp = normalize_traceparent_trace_id(traceparent_header)
    if from_tp:
        return from_tp
    if existing and len(existing) >= 8:
        return existing
    return generate_request_trace_id()
