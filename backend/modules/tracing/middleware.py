"""Attach trace id to each HTTP request for logs and downstream propagation."""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from modules.tracing.trace import ensure_trace_id


class RequestTracingMiddleware(BaseHTTPMiddleware):
    """
    Sets ``request.state.trace_id`` and echoes ``X-Trace-Id`` on the response.

    OTLP **trace** payloads are unchanged; this is for **API** request correlation only.
    """

    async def dispatch(self, request: Request, call_next: Callable[[Request], Response]) -> Response:
        trace_id = ensure_trace_id(
            getattr(request.state, "trace_id", None),
            request.headers.get("traceparent"),
        )
        request.state.trace_id = trace_id
        response = await call_next(request)
        response.headers["X-Trace-Id"] = trace_id
        return response


def new_internal_span_id() -> str:
    return uuid.UUID(bytes=secrets.token_bytes(16)).hex[:16]
