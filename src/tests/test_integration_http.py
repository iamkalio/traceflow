"""
Live stack integration tests: real HTTP to the API, Postgres, and optionally Redis/RQ.

These do **not** run by default. Start API + Postgres (+ Redis for RQ tests), then:

  cd src
  RUN_INTEGRATION=1 python3 -m pytest tests/test_integration_http.py -v -s

Optional: drain the eval queue with an in-process ``SimpleWorker`` (same Redis connection + ``Queue`` as enqueue; avoids fork/LMOVE quirks on macOS).

Environment:
  INTEGRATION_API_URL   Base URL (default http://127.0.0.1:8000)
  DATABASE_URL          Same DB the API uses (pytest does not override it)
  REDIS_URL             Required for RQ drain test (default redis://127.0.0.1:6379/0)

For eval_run jobs to finish you still need ``rq worker`` (or the drain test only runs ping jobs).
"""

from __future__ import annotations

import os
import uuid

import httpx
import pytest
from rq import Queue, SimpleWorker
from rq.job import Job

from traceflow_jobs import stable_job_id
from traceflow_jobs.client import get_redis
from traceflow_jobs.handlers import ping_job
from tests.support.otlp_export import build_minimal_otlp_body

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION"),
    reason="Set RUN_INTEGRATION=1 to run live HTTP + DB tests (see module docstring)",
)


def _base_url() -> str:
    return os.environ.get("INTEGRATION_API_URL", "http://127.0.0.1:8000").rstrip("/")


@pytest.mark.integration
def test_post_v1_traces_otlp_ingest_returns_normalized_events():
    """POST protobuf body to /v1/traces; expect 200 and normalized JSON with matching ids."""
    body, trace_id_hex, span_id_hex = build_minimal_otlp_body()
    url = f"{_base_url()}/v1/traces"

    with httpx.Client(timeout=60.0) as client:
        r = client.post(
            url,
            content=body,
            headers={"Content-Type": "application/x-protobuf"},
        )

    assert r.status_code == 200, f"ingest failed: {r.status_code} {r.text[:800]}"
    events = r.json()
    assert isinstance(events, list) and len(events) >= 1
    ev = events[0]
    assert ev.get("trace_id") == trace_id_hex
    # LLMEventNormalized uses event_id (W3C span id hex), not span_id
    assert ev.get("event_id") == span_id_hex
    assert ev.get("span_name")  # normalized OTLP span name


@pytest.mark.integration
def test_trace_ingest_then_rq_worker_runs_ping_job():
    """
    Proves Redis + worker pipeline: enqueue a unique ping job and process it with
    ``SimpleWorker`` + ``burst=True``.

    Uses one shared ``Redis`` connection and the same ``Queue`` instance for enqueue
    and the worker (avoids cases where ``get_redis()`` + ``Worker([name])`` see a
    different queue than ``enqueue_job``). ``SimpleWorker`` runs in-process (no fork),
    which is more reliable on macOS than the default ``Worker`` fork path for this test.
    Does not call OpenAI. Requires Redis reachable at REDIS_URL.
    """
    body, trace_id_hex, _span_id_hex = build_minimal_otlp_body()
    base = _base_url()

    with httpx.Client(timeout=60.0) as client:
        ir = client.post(
            f"{base}/v1/traces",
            content=body,
            headers={"Content-Type": "application/x-protobuf"},
        )
    assert ir.status_code == 200, ir.text

    unique = uuid.uuid4().hex[:12]
    job_id = stable_job_id("ping", "integration", unique)
    msg = f"integration-{unique}"

    conn = get_redis()
    qname = os.environ.get("EVAL_QUEUE_NAME", "eval")
    q = Queue(name=qname, connection=conn)
    q.enqueue(ping_job, kwargs={"msg": msg}, job_id=job_id)
    assert q.count >= 1, (
        "job was not pushed to the Redis queue; check REDIS_URL / EVAL_QUEUE_NAME "
        "matches the API worker"
    )

    worker = SimpleWorker([q], connection=conn)
    worker.work(burst=True, with_scheduler=False)

    job = Job.fetch(job_id, connection=conn)
    assert job.is_finished, job.exc_info or job.get_status()
    assert job.result == msg
