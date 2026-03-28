"""LLM-as-judge for groundedness (single structured JSON response)."""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

logger = logging.getLogger(__name__)


class GroundednessJudgeOutput(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    label: Literal["grounded", "partially_grounded", "not_grounded"]
    reason: str = Field(min_length=1, max_length=4000)
    prompt_improvement: str = ""
    context_improvement: str = ""
    failure_type: str = "unspecified"
    suggested_fix: str = ""

    @field_validator("reason", mode="before")
    @classmethod
    def reason_str(cls, v: Any) -> str:
        if v is None:
            return "No reason provided."
        return str(v).strip() or "No reason provided."

    @field_validator("prompt_improvement", "context_improvement", mode="before")
    @classmethod
    def opt_str(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v).strip()[:2000]

    @field_validator("failure_type", mode="before")
    @classmethod
    def failure_slug(cls, v: Any) -> str:
        if v is None:
            return "unspecified"
        s = str(v).strip().lower().replace(" ", "_")[:64]
        return s or "unspecified"

    @field_validator("suggested_fix", mode="before")
    @classmethod
    def suggested_fix_str(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v).strip()[:2000]


@dataclass(frozen=True)
class GroundednessJudgeResult:
    """Validated judge output plus raw model text for observability."""

    output: GroundednessJudgeOutput
    raw_response: str
    cost_usd: float | None = None
    latency_ms: int | None = None


class GroundednessParseError(Exception):
    """Model returned text that could not be parsed into the expected JSON schema."""

    def __init__(self, message: str, *, raw_content: str | None, cause: Exception | None) -> None:
        super().__init__(message)
        self.raw_content = raw_content
        self.cause = cause


def is_transient_openai_error(exc: BaseException) -> bool:
    """Errors where retrying the same request may succeed (RQ job retry)."""
    try:
        from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError
    except ImportError:
        return False
    if isinstance(exc, (APIConnectionError, APITimeoutError, RateLimitError)):
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code in (408, 429, 500, 502, 503, 504)
    return False


def build_groundedness_prompt(*, context: str, response: str) -> str:
    return f"""You are an evaluator for AI-generated responses.

Your task is to determine whether the response is grounded in the provided context.

Rules:
- Only use the provided context to judge correctness.
- If the response contains information not present in the context, mark it as ungrounded or partially_grounded as appropriate.
- If partially grounded, reflect that in the score.

Return JSON ONLY with keys score, label, reason, prompt_improvement, context_improvement, failure_type, suggested_fix and no other text:
- score: number from 0.0 to 1.0
- label: one of grounded, partially_grounded, not_grounded
- reason: short explanation of the verdict
- prompt_improvement: one or two sentences on how to improve the model/system prompt or instructions (or empty string)
- context_improvement: one or two sentences on how to improve retrieval/context quality for this kind of query (or empty string)
- failure_type: short snake_case category for dashboards (e.g. not_grounded_in_context, partial_grounding, unsupported_claim, insufficient_context, other). If label is grounded, use ok or grounded.
- suggested_fix: one concise sentence on what to change (prompt, retrieval, or product behavior), or empty string

Context:
{context}

Response:
{response}
"""


def _estimate_chat_cost_usd(*, model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Rough USD cost from token usage (override via env for custom pricing)."""
    custom = os.environ.get("OPENAI_EVAL_COST_PER_1M_PROMPT_USD")
    custom_out = os.environ.get("OPENAI_EVAL_COST_PER_1M_COMPLETION_USD")
    m = (model or "").lower()
    if custom and custom_out:
        inp = float(custom)
        out = float(custom_out)
    elif "gpt-4o-mini" in m:
        inp, out = 0.15, 0.60
    elif "gpt-4o" in m and "mini" not in m:
        inp, out = 2.50, 10.00
    else:
        inp, out = 0.15, 0.60
    return (max(0, prompt_tokens) * inp + max(0, completion_tokens) * out) / 1_000_000.0


def call_groundedness_judge(
    *, context: str, response: str, api_key: str | None = None
) -> GroundednessJudgeResult:
    from openai import OpenAI

    resolved = (api_key or os.environ.get("OPENAI_API_KEY") or "").strip()
    if not resolved:
        raise RuntimeError("OPENAI_API_KEY is not set")

    model = os.environ.get("OPENAI_EVAL_MODEL", "gpt-4o-mini")
    prompt = build_groundedness_prompt(context=context, response=response)
    client = OpenAI(api_key=resolved)

    last_raw: str | None = None
    last_parse_err: Exception | None = None

    for attempt in range(2):
        try:
            t0 = time.perf_counter()
            completion = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                max_tokens=700,
                temperature=0.0,
            )
            latency_ms = int((time.perf_counter() - t0) * 1000)
            raw = (completion.choices[0].message.content or "").strip()
            last_raw = raw
            if not raw:
                raise ValueError("empty model content")
            out = GroundednessJudgeOutput.model_validate_json(raw)
            usage = completion.usage
            pt = int(getattr(usage, "prompt_tokens", None) or 0) if usage else 0
            ct = int(getattr(usage, "completion_tokens", None) or 0) if usage else 0
            cost = _estimate_chat_cost_usd(model=model, prompt_tokens=pt, completion_tokens=ct)
            return GroundednessJudgeResult(
                output=out, raw_response=raw, cost_usd=cost, latency_ms=latency_ms
            )
        except (json.JSONDecodeError, ValidationError, ValueError) as e:
            last_parse_err = e
            logger.warning(
                "groundedness judge parse attempt %s failed: %s raw_preview=%r",
                attempt + 1,
                e,
                (last_raw or "")[:400],
            )
        except Exception as e:
            if is_transient_openai_error(e):
                logger.warning(
                    "groundedness judge transient OpenAI error (will retry job): %s",
                    e,
                )
                raise
            logger.warning("groundedness judge non-retryable error: %s", e)
            raise

    raise GroundednessParseError(
        f"Judge output invalid after retries: {last_parse_err}",
        raw_content=last_raw,
        cause=last_parse_err,
    )
