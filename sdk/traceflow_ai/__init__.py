"""Instrument LLM calls and send traces to your observability dashboard (Traceflow AI)."""

from .config import get
from .sender import build_trace, send_trace

__all__ = ["init", "build_trace", "send_trace"]


def init(
    endpoint: str,
    *,
    enabled: bool = True,
    attributes: dict | None = None,
    patch_openai: bool = True,
) -> None:
    """
    Configure the SDK and optionally patch OpenAI so traces are sent automatically.

    Args:
        endpoint: Dashboard API base URL (e.g. http://localhost:8000).
        enabled: If False, no traces are sent.
        attributes: Extra key-value pairs attached to every trace.
        patch_openai: If True, openai.chat.completions.create is wrapped to capture and send traces.
    """
    cfg = get()
    cfg["endpoint"] = endpoint.rstrip("/")
    cfg["enabled"] = enabled
    if attributes is not None:
        cfg["attributes"] = attributes
    if patch_openai:
        from . import openai_patch
        openai_patch._patch_openai()
