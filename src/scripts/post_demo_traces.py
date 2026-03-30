#!/usr/bin/env python3
"""
Post demo traces to Traceflow.

Why this exists:
- /v1/traces ingests OTLP protobuf (not JSON).
- For demos, it's helpful to have one clearly grounded trace and one clearly ungrounded trace.

Usage:
  pip install httpx opentelemetry-proto
  BASE_URL=http://127.0.0.1:8000 OPENAI_API_KEY=sk-... PYTHONPATH=src python3 src/scripts/post_demo_traces.py

What you'll get:
- Two new traces in the UI with realistic support scenarios
- Then you can run groundedness from the UI to demo scores/labels/reasoning
"""

from __future__ import annotations

import os
import sys
import time
import uuid
from dataclasses import dataclass

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


def _kv_float(key: str, value: float) -> KeyValue:
    kv = KeyValue(key=key)
    kv.value.CopyFrom(AnyValue(double_value=value))
    return kv


@dataclass(frozen=True)
class DemoTrace:
    title: str
    prompt: str
    output: str
    context: str
    status: str = "success"


def _build_export_request(demo: DemoTrace) -> tuple[ExportTraceServiceRequest, str, str]:
    """One llm_call span; returns (request, trace_id_hex, span_id_hex)."""
    trace_id_hex = uuid.uuid4().hex
    span_id_hex = uuid.uuid4().hex[:16]

    req = ExportTraceServiceRequest()
    rs = ResourceSpans()
    rs.resource.CopyFrom(
        Resource(
            attributes=[
                _kv_str("service.name", "demo.app"),
                _kv_str("deployment.environment", "demo"),
                _kv_str("app.version", "1.0.0-demo"),
            ]
        )
    )

    ss = ScopeSpans()
    span = Span()
    span.trace_id = bytes.fromhex(trace_id_hex)
    span.span_id = bytes.fromhex(span_id_hex)
    span.name = f"demo.llm_call.{demo.title}"

    now_ns = time.time_ns()
    span.start_time_unix_nano = now_ns
    span.end_time_unix_nano = now_ns + 220_000_000  # 220ms

    prompt_tokens = max(24, int(len(demo.prompt) / 4))
    completion_tokens = max(24, int(len(demo.output) / 4))
    total_tokens = prompt_tokens + completion_tokens

    attrs = [
        _kv_str("traceflow.type", "llm_call"),
        _kv_str("traceflow.model", "gpt-4o-mini"),
        _kv_str("traceflow.input", demo.prompt),
        _kv_str("traceflow.output", demo.output),
        _kv_int("traceflow.latency_ms", 220),
        _kv_float("traceflow.cost_usd", 0.0024),
        _kv_int("traceflow.usage.prompt_tokens", prompt_tokens),
        _kv_int("traceflow.usage.completion_tokens", completion_tokens),
        _kv_int("traceflow.usage.total_tokens", total_tokens),
        _kv_str("traceflow.status", demo.status),
        _kv_str("traceflow.meta.context", demo.context),
        _kv_str("traceflow.meta.route", "/demo/support"),
        _kv_str("app.trace_name", f"Demo: {demo.title}"),
        _kv_str("app.user_id", "demo-user-001"),
        _kv_str("app.session_id", "demo-session-001"),
    ]
    span.attributes.extend(attrs)

    ss.spans.append(span)
    rs.scope_spans.append(ss)
    req.resource_spans.append(rs)
    return req, trace_id_hex, span_id_hex


def _post_otlp(base: str, demo: DemoTrace) -> str:
    req, trace_id_hex, span_id_hex = _build_export_request(demo)
    body = req.SerializeToString()
    print(f"POST {base}/v1/traces  ({demo.title}) trace_id={trace_id_hex} span_id={span_id_hex}")
    with httpx.Client(timeout=60.0) as client:
        r = client.post(
            f"{base}/v1/traces",
            content=body,
            headers={"Content-Type": "application/x-protobuf"},
        )
    r.raise_for_status()
    events = r.json()
    if not events:
        raise RuntimeError("Empty ingest response (no normalized events returned).")
    return str(events[0].get("trace_id") or trace_id_hex)


def _queue_eval(base: str, trace_id: str, api_key: str, eval_name: str = "groundedness_v1") -> None:
    with httpx.Client(timeout=60.0) as client:
        r = client.post(
            f"{base}/v1/traces/{trace_id}/evals/run",
            json={"eval_name": eval_name},
            headers={"X-OpenAI-API-Key": api_key},
        )
    r.raise_for_status()


def main() -> int:
    base = os.environ.get("BASE_URL", "http://127.0.0.1:8000").rstrip("/")

    grounded = DemoTrace(
        title="return_window_and_shipping",
        prompt=(
            "I bought the wrong size. What's your return window and do I have to pay for shipping? "
            "Please answer in 2-3 bullets."
        ),
        context=(
            "Store policy (Acme Outfitters): Returns accepted within 30 days of delivery if items are unused "
            "and in original packaging. Return shipping is free for customers in the US; outside the US, "
            "return shipping is paid by the customer. Refunds are issued to the original payment method "
            "within 5-7 business days after the return is received."
        ),
        output=(
            "- You can return unused items in original packaging within 30 days of delivery.\n"
            "- Return shipping is free in the US; outside the US you cover return shipping.\n"
            "- Refunds go back to the original payment method 5–7 business days after we receive the return."
        ),
    )

    ungrounded = DemoTrace(
        title="no_receipt_and_90_day_returns",
        prompt=(
            "I lost my receipt. Can I still return this, and how long do I have? "
            "Also confirm if you offer 90-day returns."
        ),
        context=(
            "Store policy (Acme Outfitters): Returns accepted within 30 days of delivery if items are unused "
            "and in original packaging. A receipt or order number is required to process returns. "
            "Return shipping is free for customers in the US."
        ),
        output=(
            "Yes — you can return items for up to 90 days even without a receipt. "
            "Just bring the item in and we’ll refund you to any payment method you prefer."
        ),
    )

    demos = [grounded, ungrounded]

    trace_ids: list[str] = []
    for d in demos:
        trace_ids.append(_post_otlp(base, d))

    print("\nPosted demo traces (now run groundedness from the UI):")
    for d, tid in zip(demos, trace_ids, strict=True):
        print(f"- {d.title}: {tid}")
    print("\nOpen Traces in the UI and you should see scores populate as jobs complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

