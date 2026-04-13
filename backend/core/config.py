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


def github_client_id() -> str:
    return os.environ.get("GITHUB_CLIENT_ID", "")


def github_client_secret() -> str:
    return os.environ.get("GITHUB_CLIENT_SECRET", "")


def jwt_secret() -> str:
    return os.environ.get("JWT_SECRET", "change-me-in-production-use-a-long-random-string")


def frontend_url() -> str:
    return os.environ.get("FRONTEND_URL", "http://localhost:3000")
