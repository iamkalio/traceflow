"""Failure-type clustering from eval run context (product insights)."""

from __future__ import annotations

from typing import Any, Iterable


def aggregate_failure_types_from_contexts(contexts: Iterable[dict[str, Any]]) -> dict[str, int]:
    """
    Count ``failure_type`` values from eval_run.context dicts (excluding generic placeholders).
    """
    counts: dict[str, int] = {}
    for ctx in contexts:
        ft = ctx.get("failure_type")
        if isinstance(ft, str) and ft.strip():
            key = ft.strip().lower()[:128]
            if key == "unspecified":
                continue
            counts[key] = counts.get(key, 0) + 1
    return counts


def top_failure_types(counts: dict[str, int], *, limit: int = 15) -> list[dict[str, int | str]]:
    pairs = sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:limit]
    return [{"failure_type": k, "count": v} for k, v in pairs]
