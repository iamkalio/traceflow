"""Environment-backed settings."""

from __future__ import annotations

import os


def database_url() -> str:
    return os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg://traceflow:traceflow@localhost:5432/traceflow",
    )


def redis_url() -> str:
    return os.environ.get("REDIS_URL", "redis://localhost:6379/0")


def eval_queue_name() -> str:
    return os.environ.get("EVAL_QUEUE_NAME", "eval")
