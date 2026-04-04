"""Ingestion orchestration: OTLP bytes → normalized domain events."""

from __future__ import annotations

from modules.ingestion.processor import export_request_to_llm_events, parse_export_trace_service_request
from modules.ingestion.schemas import LLMEventNormalized


def ingest_otlp_body(body: bytes) -> list[LLMEventNormalized]:
    """Parse OTLP ExportTraceServiceRequest bytes and return normalized LLM events."""
    req = parse_export_trace_service_request(body)
    return export_request_to_llm_events(req)
