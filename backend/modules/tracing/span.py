"""Lightweight span context for logging (expand to OTel SDK later)."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass

_span_stack: ContextVar[list["Span"]] = ContextVar("traceflow_span_stack", default=[])


@dataclass(frozen=True)
class Span:
    name: str
    trace_id: str
    span_id: str


def current_span() -> Span | None:
    stack = _span_stack.get()
    return stack[-1] if stack else None


def push_span(span: Span) -> None:
    stack = list(_span_stack.get())
    stack.append(span)
    _span_stack.set(stack)


def pop_span() -> None:
    stack = list(_span_stack.get())
    if stack:
        stack.pop()
        _span_stack.set(stack)
