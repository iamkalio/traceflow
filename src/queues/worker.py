from __future__ import annotations
import os
from rq import Worker

from queues.client import get_redis, queue_name


def main() -> None:
    queues = [queue_name()]
    Worker(queues, connection=get_redis()).work(with_scheduler=False)


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    main()
