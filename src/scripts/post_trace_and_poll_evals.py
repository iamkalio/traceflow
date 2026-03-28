#!/usr/bin/env python3
"""
POST a minimal OTLP trace (one llm_call span with optional retrieval context) to /v1/traces,
then poll GET /v1/traces/{trace_id}/evals until groundedness appears or timeout.

Requires: API + Postgres + Redis + worker running (same as docker compose stack).

Usage (from repo root or from src/):
  pip install httpx  # or: already satisfied if you use dev extras
  PYTHONPATH=src python scripts/post_trace_and_poll_evals.py
  BASE_URL=http://localhost:8000 PYTHONPATH=src python scripts/post_trace_and_poll_evals.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid

# Ensure src is on path when run as python scripts/post_trace_and_poll_evals.py from src/
_SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

try:
    import httpx
except ImportError:
    print("Install httpx: pip install httpx", file=sys.stderr)
    raise SystemExit(1)

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


def build_export_request() -> tuple[ExportTraceServiceRequest, str, str]:
    """One llm_call span; returns (request, trace_id_hex, span_id_hex)."""
    trace_id_hex = uuid.uuid4().hex
    span_id_hex = uuid.uuid4().hex[:16]

    req = ExportTraceServiceRequest()
    rs = ResourceSpans()
    rs.resource.CopyFrom(Resource(attributes=[_kv_str("service.name", "post_trace_script")]))

    ss = ScopeSpans()
    span = Span()
    span.trace_id = bytes.fromhex(trace_id_hex)
    span.span_id = bytes.fromhex(span_id_hex)
    span.name = "script.llm_call"

    now_ns = time.time_ns()
    span.start_time_unix_nano = now_ns
    span.end_time_unix_nano = now_ns + 50_000_000

    attrs = [
        _kv_str("traceflow.type", "llm_call"),
        _kv_str("traceflow.model", "gpt-4o-mini"),
        _kv_str("traceflow.input", "What is 2+2? this is a long input to test the UI and see how it reacts with the coulmn "),
        _kv_str("traceflow.output", "Four."),
        _kv_int("traceflow.latency_ms", 42),
        _kv_str("traceflow.status", "success"),
        _kv_str("traceflow.meta.context", "Arithmetic: 2 + 2 equals 4."),
        _kv_str("traceflow.meta.route", "/scripts/demo"),
    ]
    span.attributes.extend(attrs)
    ss.spans.append(span)
    rs.scope_spans.append(ss)
    req.resource_spans.append(rs)
    return req, trace_id_hex, span_id_hex


def main() -> int:
    base = os.environ.get("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    timeout = float(os.environ.get("POLL_TIMEOUT_SEC", "90"))

    otlp_req, trace_id_hex, span_id_hex = build_export_request()
    body = otlp_req.SerializeToString()

    print(f"POST {base}/v1/traces  (trace_id={trace_id_hex} span_id={span_id_hex})")
    with httpx.Client(timeout=60.0) as client:
        r = client.post(
            f"{base}/v1/traces",
            content=body,
            headers={"Content-Type": "application/x-protobuf"},
        )
    if r.status_code != 200:
        print(f"FAIL ingest HTTP {r.status_code}: {r.text[:500]}", file=sys.stderr)
        return 1

    events = r.json()
    print("ingest response:", json.dumps(events, indent=2)[:2000])
    if not events:
        print("FAIL: empty ingest response", file=sys.stderr)
        return 1

    tid = events[0].get("trace_id") or trace_id_hex
    print(f"\nPolling GET {base}/v1/traces/{tid}/evals?eval_name=groundedness (up to {timeout}s)…")

    deadline = time.monotonic() + timeout
    last_count = 0
    while time.monotonic() < deadline:
        with httpx.Client(timeout=30.0) as client:
            er = client.get(f"{base}/v1/traces/{tid}/evals", params={"eval_name": "groundedness"})
        if er.status_code == 404:
            print("FAIL: trace not found on eval endpoint (DB mismatch?)", file=sys.stderr)
            return 1
        if er.status_code != 200:
            print(f"FAIL evals HTTP {er.status_code}: {er.text[:500]}", file=sys.stderr)
            return 1
        evals = er.json()
        if len(evals) > last_count:
            print(json.dumps(evals, indent=2, default=str))
            last_count = len(evals)
        if evals:
            print("\nOK — groundedness row present. Check label/score/reason above.")
            if evals[0].get("label") == "skipped" and "OPENAI_API_KEY" in (evals[0].get("reason") or ""):
                print("\nNote: worker skipped judge (no OPENAI_API_KEY in worker env).")
            return 0
        time.sleep(1.5)

    print(
        "TIMEOUT: no eval_results yet. Is the worker running with Redis + DB?",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
