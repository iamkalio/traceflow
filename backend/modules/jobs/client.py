from __future__ import annotations

import hashlib
import os
import secrets
from typing import Any, Callable, Union

import redis
from rq import Queue
from rq.job import Retry

EVAL_RUN_JOB = "modules.jobs.tasks.eval_tasks.eval_run_job"

_EVAL_KEY_PREFIX = "eval:key:"
_EVAL_KEY_TTL_S = 300  # 5 minutes — enough for the job to be picked up


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


def store_eval_key(openai_api_key: str) -> str:
    """Store the API key in Redis under a one-time token with a short TTL.

    Returns the token to embed in job kwargs instead of the raw key,
    so the key never appears in serialised RQ job data.
    """
    token = secrets.token_hex(32)
    get_redis().setex(f"{_EVAL_KEY_PREFIX}{token}", _EVAL_KEY_TTL_S, openai_api_key)
    return token


def fetch_and_delete_eval_key(token: str) -> str | None:
    """Fetch the API key by token and delete it atomically.

    Returns None if the token has expired or was already consumed.
    Uses GETDEL (Redis 6.2+) for a single round-trip.
    """
    raw = get_redis().getdel(f"{_EVAL_KEY_PREFIX}{token}")
    if raw is None:
        return None
    return raw.decode() if isinstance(raw, bytes) else raw


def enqueue_job(
    func: Union[Callable[..., Any], str],
    *,
    job_id: str,
    kwargs: dict[str, Any],
    retry: Retry | None = None,
    description: str | None = None,
) -> str:
    """If ``description`` is set, RQ uses it in logs instead of ``get_call_string()`` (which embeds kwargs)."""
    q = get_queue()
    if description is not None:
        job = q.enqueue(func, kwargs=kwargs, job_id=job_id, retry=retry, description=description)
    else:
        job = q.enqueue(func, kwargs=kwargs, job_id=job_id, retry=retry)
    return job.id
