import time

from .config import get
from .sender import build_trace, send_trace

# Default price per 1k tokens (input, output) for cost estimate
_PRICES: dict[str, tuple[float, float]] = {
    "gpt-4o": (0.0025, 0.01),
    "gpt-4o-mini": (0.00015, 0.0006),
    "gpt-4-turbo": (0.01, 0.03),
}


def _cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    if model not in _PRICES:
        return 0.0
    inp, out = _PRICES[model]
    return (prompt_tokens * inp + completion_tokens * out) / 1000.0


def _patch_openai() -> None:
    try:
        from openai.resources.chat import completions as comp_mod
        Completions = comp_mod.Completions
    except ImportError:
        return
    if getattr(Completions, "_traceflow_ai_patched", False):
        return

    _create = Completions.create

    def _wrapped_create(self, *args, **kwargs):
        start = time.perf_counter()
        cfg = get()
        model_arg = kwargs.get("model") or (args[0] if args else "")
        messages = kwargs.get("messages") or []
        prompt = str(messages)
        try:
            resp = _create(self, *args, **kwargs)
            if not cfg["endpoint"] or not cfg["enabled"]:
                return resp
            try:
                model = model_arg or getattr(resp, "model", "")
                choice = resp.choices[0] if resp.choices else None
                completion = choice.message.content if choice and choice.message else ""
                usage = getattr(resp, "usage", None)
                pt = getattr(usage, "prompt_tokens", 0) or 0
                ct = getattr(usage, "completion_tokens", 0) or 0
                latency_ms = int((time.perf_counter() - start) * 1000)
                cost = _cost(model, pt, ct)
                trace = build_trace(
                    model=model,
                    prompt=prompt,
                    completion=completion,
                    prompt_tokens=pt,
                    completion_tokens=ct,
                    cost_usd=round(cost, 6),
                    latency_ms=latency_ms,
                )
                send_trace(trace)
            except Exception:
                pass
            return resp
        except Exception as e:
            if cfg["endpoint"] and cfg["enabled"]:
                try:
                    latency_ms = int((time.perf_counter() - start) * 1000)
                    trace = build_trace(
                        model=model_arg,
                        prompt=prompt,
                        completion="",
                        status="error",
                        error=str(e),
                        latency_ms=latency_ms,
                    )
                    send_trace(trace)
                except Exception:
                    pass
            raise

    Completions.create = _wrapped_create
    Completions._traceflow_ai_patched = True
