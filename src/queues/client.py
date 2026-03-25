from __future__ import annotations

import hashlib
import os
from typing import Any, Callable

import redis
from rq import Queue


def redis_url() -> str:
    return os.environ.get("REDIS_URL", "redis://localhost:6379/0")


def queue_name() -> str:
    return os.environ.get("EVAL_QUEUE_NAME", "eval")


def get_redis() -> redis.Redis:
    # NOTE: RQ stores job data as binary; do not enable decode_responses.
    return redis.Redis.from_url(redis_url())


def get_queue() -> Queue:
    return Queue(name=queue_name(), connection=get_redis())


def stable_job_id(*parts: str) -> str:
    raw = "\n".join(parts).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:32]


def enqueue_job(func: Callable[..., Any], *, job_id: str, kwargs: dict[str, Any]) -> str:
    q = get_queue()
    job = q.enqueue(func, kwargs=kwargs, job_id=job_id)
    return job.id


def enqueue_ping() -> str:
    from queues.jobs import ping_job

    jid = stable_job_id("ping", "v1")
    return enqueue_job(ping_job, job_id=jid, kwargs={"msg": "ping"})


def enqueue_eval_span(trace_id: str, span_id: str) -> str:
    """Queue eval job: worker loads span and runs eval service (placeholder until judge)."""
    from queues.jobs import eval_span_job

    jid = stable_job_id("eval_span", "groundedness", "v1", trace_id, span_id)
    return enqueue_job(
        eval_span_job,
        job_id=jid,
        kwargs={"trace_id": trace_id, "span_id": span_id},
    )
