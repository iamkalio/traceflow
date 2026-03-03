import json
import threading
import urllib.request
import urllib.error
from datetime import datetime, timezone
from uuid import uuid4

from .config import get


def send_trace(payload: dict) -> None:
    """POST trace to ingest endpoint. Uses non-daemon thread so process waits for send on exit."""
    cfg = get()
    if not cfg["endpoint"] or not cfg["enabled"]:
        return
    url = f"{cfg['endpoint']}/api/ingest"
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    def _post() -> None:
        try:
            urllib.request.urlopen(request, timeout=5)
        except Exception:
            pass

    # Non-daemon so process waits for send to complete on exit (e.g. short scripts).
    threading.Thread(target=_post, daemon=False).start()


def _caller_name() -> str:
    """Name of the function that invoked the LLM (skips traceflow_ai/openai frames)."""
    import inspect
    try:
        for frame_info in inspect.stack():
            f = frame_info.frame
            name = frame_info.function
            mod = f.f_globals.get("__name__", "")
            if name == "_wrapped_create" or "traceflow_ai" in mod or "openai" in mod:
                continue
            if name.startswith("<"):
                continue
            return name or ""
    except Exception:
        pass
    return ""


def build_trace(
    *,
    model: str,
    prompt: str = "",
    completion: str = "",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    cost_usd: float = 0.0,
    latency_ms: int | None = None,
    status: str = "success",
    error: str | None = None,
    attributes: dict | None = None,
    name: str | None = None,
    trace_id: str | None = None,
    parent_span_id: str | None = None,
    kind: str = "llm",
) -> dict:
    """Build a span payload. Use trace_id/parent_span_id to attach to an existing trace."""
    cfg = get()
    now = datetime.now(timezone.utc).isoformat()
    tid = trace_id or str(uuid4())
    span_id = str(uuid4())
    base = {**cfg.get("attributes", {})}
    if attributes:
        base.update(attributes)
    trace_name = name if name is not None and name != "" else _caller_name()
    return {
        "trace_id": tid,
        "span_id": span_id,
        "parent_span_id": parent_span_id,
        "kind": (kind or "llm").lower(),
        "timestamp": now,
        "name": trace_name,
        "model": model,
        "prompt": prompt,
        "completion": completion,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "cost_usd": cost_usd,
        "latency_ms": latency_ms,
        "status": status,
        "error": error,
        "attributes": base,
    }
