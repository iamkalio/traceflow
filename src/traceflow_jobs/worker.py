from __future__ import annotations

import importlib
import logging
import os

from rq import Worker

from traceflow_jobs.client import EVAL_RUN_JOB, get_redis, queue_name

logger = logging.getLogger(__name__)


def _assert_job_handlers_importable() -> None:
    """Fail fast with a clear error if the worker image cannot load RQ job entrypoints."""
    mod = importlib.import_module("traceflow_jobs.handlers")
    for name in ("ping_job", "eval_span_job", "eval_run_job"):
        fn = getattr(mod, name, None)
        if not callable(fn):
            raise RuntimeError(
                f"traceflow_jobs.handlers.{name} is missing or not callable "
                f"(rebuild worker; PYTHONPATH must include src). Got: {fn!r}"
            )
    # Ensure the string path RQ uses resolves (same as job.perform())
    from rq.utils import import_attribute

    import_attribute(EVAL_RUN_JOB)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    _assert_job_handlers_importable()
    logger.info("RQ job handlers loaded from traceflow_jobs.handlers")
    qlist = [queue_name()]
    # Extra safety: if a job ever lacks a custom description, avoid printing full kwargs to logs.
    log_jobs = os.environ.get("RQ_LOG_JOB_DESCRIPTION", "1").strip().lower() not in ("0", "false", "no")
    Worker(qlist, connection=get_redis(), log_job_description=log_jobs).work(with_scheduler=False)


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    main()
