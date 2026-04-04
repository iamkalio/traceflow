"""
Lightweight in-process metrics (replace with Prometheus / OTel exporter later).

Counters and simple histograms are enough to prove "we measure behavior" in dev and tests.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Any

_lock = threading.Lock()


@dataclass
class MetricsRegistry:
    counters: dict[str, int] = field(default_factory=dict)
    # recent eval job latencies (ms), bounded
    eval_latencies_ms: deque[float] = field(default_factory=lambda: deque(maxlen=500))
    cache_hits: int = 0
    cache_misses: int = 0
    eval_failures: int = 0
    eval_completions: int = 0

    def incr(self, name: str, n: int = 1) -> None:
        with _lock:
            self.counters[name] = self.counters.get(name, 0) + n

    def observe_eval_latency_ms(self, ms: float | None) -> None:
        if ms is None:
            return
        with _lock:
            self.eval_latencies_ms.append(float(ms))

    def record_cache(self, hit: bool) -> None:
        with _lock:
            if hit:
                self.cache_hits += 1
            else:
                self.cache_misses += 1

    def record_eval_terminal(self, *, failed: bool) -> None:
        with _lock:
            if failed:
                self.eval_failures += 1
            else:
                self.eval_completions += 1

    def snapshot(self) -> dict[str, Any]:
        with _lock:
            lat = list(self.eval_latencies_ms)
            return {
                "counters": dict(self.counters),
                "eval_latency_ms_recent": lat,
                "eval_latency_p50_ms": _percentile(lat, 50),
                "eval_latency_p95_ms": _percentile(lat, 95),
                "cache_hits": self.cache_hits,
                "cache_misses": self.cache_misses,
                "eval_failures": self.eval_failures,
                "eval_completions": self.eval_completions,
            }


def _percentile(sorted_or_seq: list[float], p: int) -> float | None:
    if not sorted_or_seq:
        return None
    xs = sorted(sorted_or_seq)
    k = (len(xs) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(xs) - 1)
    if f == c:
        return xs[f]
    return xs[f] + (xs[c] - xs[f]) * (k - f)


GLOBAL_METRICS = MetricsRegistry()


def record_wall_ms(metric_name: str, elapsed_ms: float) -> None:
    """Record one wall-clock observation (e.g. request or eval phase)."""
    GLOBAL_METRICS.incr(f"{metric_name}_calls")
    GLOBAL_METRICS.observe_eval_latency_ms(elapsed_ms)
