"""
OTLP/HTTP trace export → normalized LLM events.

Parent resolution for app.* fields: use span attributes first; if missing, use the
parent span’s attributes from the same ingest batch (matched by parent_span_id bytes);
if still missing, use resource attributes.

event_id: hex-encoded span_id bytes (W3C uses 8-byte span_id → 16 hex chars). If span_id
is empty, a UUID4 string is used.

Example — input attribute map (string values) and normalized JSON:

    attrs = {
        "traceflow.type": "llm_call",
        "traceflow.model": "gpt-4o-mini",
        "traceflow.input": "Hello",
        "traceflow.output": "Hi there",
        "traceflow.latency_ms": 120,
        "traceflow.cost_usd": 0.0001,
        "traceflow.status": "success",
        "traceflow.usage.prompt_tokens": 5,
        "traceflow.usage.completion_tokens": 3,
        "traceflow.usage.total_tokens": 8,
        "traceflow.meta.route": "/chat",
        "app.user_id": "u-1",
    }

    # Normalized (illustrative; trace_id/parent/event_id come from span context bytes):

    {
      "event_id": "a1b2c3d4e5f67890",
      "trace_id": "..." ,
      "parent_span_id": null,
      "span_name": "chat.completion",
      "model": "gpt-4o-mini",
      "input": "Hello",
      "output": "Hi there",
      "latency_ms": 120,
      "cost_usd": 0.0001,
      "prompt_tokens": 5,
      "completion_tokens": 3,
      "total_tokens": 8,
      "status": "success",
      "error": null,
      "created_at": "2025-03-24T12:00:00.000Z",
      "resource": {"service.name": "my-app"},
      "metadata": {
        "user_id": "u-1",
        "route": "/chat",
        "unknown_attributes": {"some.vendor.key": "x"}
      },
      "tenant_id": null
    }
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from google.protobuf.message import DecodeError
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, KeyValue
from opentelemetry.proto.trace.v1.trace_pb2 import Span

from modules.ingestion.schemas import LLMEventNormalized

logger = logging.getLogger(__name__)

# Keys fully consumed by mapping (not placed in unknown_attributes)
_TRACE_CANONICAL_PREFIXES = (
    "traceflow.type",
    "traceflow.model",
    "traceflow.input",
    "traceflow.output",
    "traceflow.latency_ms",
    "traceflow.cost_usd",
    "traceflow.status",
    "traceflow.error",
)
_TRACE_USAGE_KEYS = (
    "traceflow.usage.prompt_tokens",
    "traceflow.usage.completion_tokens",
    "traceflow.usage.total_tokens",
)
_TRACE_META_PREFIX = "traceflow.meta."
_APP_METADATA_KEYS = (
    "app.user_id",
    "app.session_id",
    "app.trace_name",
    "app.version",
    "app.tags",
    "app.tenant_id",
)
_APP_META_PREFIX = "app.meta."


def bytes_to_hex(b: bytes) -> str:
    return b.hex() if b else ""


def _nano_to_rfc3339_utc(nano: int) -> str:
    # 0 ns since epoch is valid (1970-01-01); do not use `not nano`.
    # OTLP uses uint64 with no proto3 presence, so unset spans also surface as 0.
    dt = datetime.fromtimestamp(nano / 1e9, tz=timezone.utc)
    s = dt.isoformat(timespec="milliseconds")
    if s.endswith("+00:00"):
        return s[:-6] + "Z"
    return s


def any_value_to_python(any_val: AnyValue) -> Any:
    which = any_val.WhichOneof("value")
    if which is None:
        return None
    if which == "string_value":
        return any_val.string_value
    if which == "bool_value":
        return any_val.bool_value
    if which == "int_value":
        return any_val.int_value
    if which == "double_value":
        return any_val.double_value
    if which == "bytes_value":
        return any_val.bytes_value.decode("utf-8", errors="replace")
    if which == "array_value":
        return [any_value_to_python(v) for v in any_val.array_value.values]
    if which == "kvlist_value":
        return {kv.key: any_value_to_python(kv.value) for kv in any_val.kvlist_value.values}
    return str(any_val)


def key_values_to_map(kvs: list[KeyValue]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for kv in kvs:
        out[kv.key] = any_value_to_python(kv.value)
    return out


def parse_export_trace_service_request(body: bytes) -> ExportTraceServiceRequest:
    req = ExportTraceServiceRequest()
    try:
        req.ParseFromString(body)
    except DecodeError as e:
        raise ValueError(f"Invalid OTLP protobuf: {e}") from e
    return req


def _get_first(
    key: str,
    span_attrs: dict[str, Any],
    parent_attrs: dict[str, Any] | None,
    resource_attrs: dict[str, Any],
) -> Any:
    if key in span_attrs and span_attrs[key] is not None and span_attrs[key] != "":
        return span_attrs[key]
    if parent_attrs and key in parent_attrs and parent_attrs[key] is not None and parent_attrs[key] != "":
        return parent_attrs[key]
    return resource_attrs.get(key)


def _build_span_index(
    req: ExportTraceServiceRequest,
) -> dict[str, dict[str, Any]]:
    """Map span_id hex → flat attribute map for parent resolution within the batch."""
    index: dict[str, dict[str, Any]] = {}
    for rs in req.resource_spans:
        for ss in rs.scope_spans:
            for span in ss.spans:
                sid = bytes_to_hex(span.span_id)
                if sid:
                    index[sid] = key_values_to_map(list(span.attributes))
    return index


def _resource_subset(resource_attrs: dict[str, Any]) -> dict[str, Any]:
    keys = ("service.name", "service.version", "deployment.environment", "app.tenant_id")
    return {k: resource_attrs[k] for k in keys if k in resource_attrs}


def _collect_traceflow_metadata(span_attrs: dict[str, Any]) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    for k, v in list(span_attrs.items()):
        if k.startswith(_TRACE_META_PREFIX):
            remainder = k[len(_TRACE_META_PREFIX) :]
            meta[remainder] = v if isinstance(v, str) else json.dumps(v)
    return meta


def _collect_app_metadata(
    span_attrs: dict[str, Any],
    parent_attrs: dict[str, Any] | None,
    resource_attrs: dict[str, Any],
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in _APP_METADATA_KEYS:
        val = _get_first(key, span_attrs, parent_attrs, resource_attrs)
        if val is not None and val != "":
            short = key.split(".", 1)[-1]
            out[short] = val
    # app.meta.* on span or parent
    for src in (span_attrs, parent_attrs or {}):
        for k, v in src.items():
            if k.startswith(_APP_META_PREFIX):
                remainder = k[len(_APP_META_PREFIX) :]
                out[f"meta_{remainder}"] = v if isinstance(v, str) else json.dumps(v)
    return out


def _is_traceflow_llm(span_attrs: dict[str, Any]) -> bool:
    t = span_attrs.get("traceflow.type")
    return isinstance(t, str) and t == "llm_call"


def _map_traceflow_core(span_attrs: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": span_attrs.get("traceflow.model"),
        "input": span_attrs.get("traceflow.input"),
        "output": span_attrs.get("traceflow.output"),
        "latency_ms": span_attrs.get("traceflow.latency_ms"),
        "cost_usd": span_attrs.get("traceflow.cost_usd"),
        "status": span_attrs.get("traceflow.status"),
        "error": span_attrs.get("traceflow.error"),
        "prompt_tokens": span_attrs.get("traceflow.usage.prompt_tokens"),
        "completion_tokens": span_attrs.get("traceflow.usage.completion_tokens"),
        "total_tokens": span_attrs.get("traceflow.usage.total_tokens"),
    }


def _consumed_keys(span_attrs: dict[str, Any]) -> set[str]:
    consumed: set[str] = set()
    for k in span_attrs:
        if k.startswith(_TRACE_META_PREFIX):
            consumed.add(k)
    consumed.update(_TRACE_CANONICAL_PREFIXES)
    consumed.update(_TRACE_USAGE_KEYS)
    return consumed


def _unknown_attributes(
    span_attrs: dict[str, Any],
    consumed: set[str],
) -> dict[str, Any]:
    unk: dict[str, Any] = {}
    for k, v in span_attrs.items():
        if k in consumed:
            continue
        if k.startswith(_APP_META_PREFIX):
            continue
        if k in _APP_METADATA_KEYS:
            continue
        unk[k] = v
    return unk


def normalize_span(
    span: Span,
    resource_attrs: dict[str, Any],
    span_index: dict[str, dict[str, Any]],
) -> LLMEventNormalized | None:
    span_attrs = key_values_to_map(list(span.attributes))
    parent_hex = bytes_to_hex(span.parent_span_id)
    parent_attrs = span_index.get(parent_hex) if parent_hex else None

    if not _is_traceflow_llm(span_attrs):
        return None

    core = _map_traceflow_core(span_attrs)
    consumed = _consumed_keys(span_attrs)
    unknown = _unknown_attributes(span_attrs, consumed)
    tf_meta = _collect_traceflow_metadata(span_attrs)
    app_meta = _collect_app_metadata(span_attrs, parent_attrs, resource_attrs)

    metadata: dict[str, Any] = {**tf_meta, **app_meta}
    if unknown:
        metadata["unknown_attributes"] = unknown

    trace_hex = bytes_to_hex(span.trace_id)
    span_hex = bytes_to_hex(span.span_id)
    event_id = span_hex if span_hex else str(uuid.uuid4())

    parent_out = parent_hex if parent_hex else None

    tenant = _get_first("app.tenant_id", span_attrs, parent_attrs, resource_attrs)
    if tenant is None or tenant == "":
        tenant = resource_attrs.get("app.tenant_id")

    resource_obj = _resource_subset(resource_attrs)

    created = _nano_to_rfc3339_utc(span.start_time_unix_nano)

    # Default status if unset
    status = core.get("status")
    if status is None or status == "":
        status = "success"

    raw = {
        "event_id": event_id,
        "trace_id": trace_hex or str(uuid.uuid4()),
        "parent_span_id": parent_out,
        "span_name": span.name or "",
        "model": core.get("model"),
        "input": core.get("input"),
        "output": core.get("output"),
        "latency_ms": core.get("latency_ms"),
        "cost_usd": core.get("cost_usd"),
        "prompt_tokens": core.get("prompt_tokens"),
        "completion_tokens": core.get("completion_tokens"),
        "total_tokens": core.get("total_tokens"),
        "status": status,
        "error": core.get("error"),
        "created_at": created,
        "resource": resource_obj,
        "metadata": metadata,
        "tenant_id": str(tenant) if tenant not in (None, "") else None,
    }
    return LLMEventNormalized.model_validate(raw)


def export_request_to_llm_events(req: ExportTraceServiceRequest) -> list[LLMEventNormalized]:
    span_index = _build_span_index(req)
    out: list[LLMEventNormalized] = []
    for rs in req.resource_spans:
        resource_attrs = key_values_to_map(list(rs.resource.attributes))
        for ss in rs.scope_spans:
            for span in ss.spans:
                ev = normalize_span(span, resource_attrs, span_index)
                if ev is not None:
                    out.append(ev)
    return out
