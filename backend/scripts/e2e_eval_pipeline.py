#!/usr/bin/env python3
"""
End-to-end: insert one LLM span (with retrieval context in metadata) → enqueue groundedness
job → RQ worker (burst) → row in eval_results (eval_name=groundedness).

With OPENAI_API_KEY set you should see a real score/label; without it, label=skipped.

Run from repo root:
  docker compose up -d postgres redis
  cd backend && alembic -c alembic.ini upgrade head
  PYTHONPATH=. python scripts/e2e_eval_pipeline.py
"""
from __future__ import annotations

import os
import sys
import uuid

# Ensure backend/ is on path when run as python scripts/e2e_eval_pipeline.py from backend/
_SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from db.repository import persist_normalized_events
from db.session import SessionLocal
from modules.ingestion.schemas import LLMEventNormalized
from modules.jobs import enqueue_eval_span


def main() -> int:
    trace_id = uuid.uuid4().hex
    span_id = uuid.uuid4().hex[:16]

    event = LLMEventNormalized(
        event_id=span_id,
        trace_id=trace_id,
        span_name="e2e.eval",
        model="test-model",
        input="What is 2+2?",
        output="Four.",
        latency_ms=42,
        status="success",
        created_at="2025-03-25T12:00:00.000Z",
        metadata={"context": "Arithmetic fact: 2 + 2 equals 4."},
    )

    session = SessionLocal()
    try:
        inserted = persist_normalized_events(session, [event])
    finally:
        session.close()

    if not inserted:
        print("FAIL: no row inserted (duplicate key?)")
        return 1

    t_id, s_id = inserted[0]
    print("inserted:")
    print(f"  trace_id={t_id}")
    print(f"  span_id={s_id}")

    job_id = enqueue_eval_span(t_id, s_id)
    print(f"enqueued job_id={job_id}")

    import redis
    from rq import Worker

    r = redis.Redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
    qname = os.environ.get("EVAL_QUEUE_NAME", "eval")
    w = Worker([qname], connection=r)
    w.work(burst=True)
    print("worker burst done")

    from sqlalchemy import text

    from db.session import engine

    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                select eval_name, eval_version, label, score, reason
                from eval_results
                where trace_id = :tid and span_id = :sid
                  and eval_name = 'groundedness' and eval_version = 'v1'
                order by created_at desc
                limit 1
                """
            ),
            {"tid": t_id, "sid": s_id},
        ).fetchone()

    if not row:
        print("FAIL: no eval_results row")
        return 1

    print(f"eval_results: {tuple(row)}")
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
