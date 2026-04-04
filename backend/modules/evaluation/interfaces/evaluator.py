"""Protocol for LLM-based evaluators (groundedness, regression, custom)."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LlmJudgeEvaluator(Protocol):
    """Minimal surface for swapping judge implementations or mocking in tests."""

    eval_name: str
    eval_version: str

    def evaluate_span(
        self,
        *,
        question: str,
        context_block: str,
        completion: str,
        api_key: str | None,
    ) -> dict[str, Any]:
        """Return a detail dict compatible with ``finalize_eval_run_from_engine_detail``."""
        ...
