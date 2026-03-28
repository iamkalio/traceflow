"""Minimal OTLP protobuf export for integration tests (one llm_call span)."""

from __future__ import annotations

import time
import uuid

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, KeyValue
from opentelemetry.proto.resource.v1.resource_pb2 import Resource
from opentelemetry.proto.trace.v1.trace_pb2 import ResourceSpans, ScopeSpans, Span


def _kv_str(key: str, value: str) -> KeyValue:
    kv = KeyValue(key=key)
    kv.value.CopyFrom(AnyValue(string_value=value))
    return kv


def _kv_int(key: str, value: int) -> KeyValue:
    kv = KeyValue(key=key)
    kv.value.CopyFrom(AnyValue(int_value=value))
    return kv


def build_minimal_otlp_body() -> tuple[bytes, str, str]:
    """
    Serialize one llm_call span. Returns (protobuf_bytes, trace_id_hex, span_id_hex).
    """
    trace_id_hex = uuid.uuid4().hex
    span_id_hex = uuid.uuid4().hex[:16]

    req = ExportTraceServiceRequest()
    rs = ResourceSpans()
    rs.resource.CopyFrom(Resource(attributes=[_kv_str("service.name", "pytest.integration")]))

    ss = ScopeSpans()
    span = Span()
    span.trace_id = bytes.fromhex(trace_id_hex)
    span.span_id = bytes.fromhex(span_id_hex)
    span.name = "integration.llm_call"

    now_ns = time.time_ns()
    span.start_time_unix_nano = now_ns
    span.end_time_unix_nano = now_ns + 50_000_000

    attrs = [
        _kv_str("traceflow.type", "llm_call"),
        _kv_str("traceflow.model", "gpt-4o-mini"),
        _kv_str("traceflow.input", "Integration test prompt."),
        _kv_str("traceflow.output", "Integration test completion."),
        _kv_int("traceflow.latency_ms", 12),
        _kv_str("traceflow.status", "success"),
        _kv_str("traceflow.meta.context", "Test context blob for groundedness."),
    ]
    span.attributes.extend(attrs)
    ss.spans.append(span)
    rs.scope_spans.append(ss)
    req.resource_spans.append(rs)
    return req.SerializeToString(), trace_id_hex, span_id_hex
