"""
Evaluation **orchestration** at the application layer.

- **domain/** — pure rules (labels, bucketing, evaluator taxonomy).
- **engine/** — external integration (OpenAI judges, parsing).
- **interfaces/** — contracts for swaps and tests.

HTTP lives in ``router.py``; RQ orchestration lives in ``modules.jobs.orchestration``.
"""

from __future__ import annotations
