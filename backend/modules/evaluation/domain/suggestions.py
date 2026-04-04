"""Turn eval outputs into actionable recommendations (pure helpers)."""

from __future__ import annotations

from typing import Any


def merge_suggestion_fields(detail: dict[str, Any]) -> str:
    """Single string for UI/snippets from engine suggestion fields."""
    parts = [
        str(detail.get("suggested_fix") or "").strip(),
        str(detail.get("prompt_improvement") or "").strip(),
        str(detail.get("context_improvement") or "").strip(),
    ]
    return "\n\n".join(p for p in parts if p)
