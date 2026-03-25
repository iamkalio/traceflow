from __future__ import annotations

import logging

from db.session import SessionLocal
from services.evals.groundedness_eval import run_groundedness_span_eval

logger = logging.getLogger(__name__)


def ping_job(msg: str = "ping") -> str:
    logger.info("ping_job: %s", msg)
    return msg


def eval_span_job(trace_id: str, span_id: str) -> str:
    """RQ processor: session + delegate to background service."""
    session = SessionLocal()
    try:
        return run_groundedness_span_eval(session, trace_id, span_id)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
