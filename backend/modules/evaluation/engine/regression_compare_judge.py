"""LLM judge: compare previous vs current model output for the same trace (regression)."""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from modules.evaluation.engine.llm_groundedness_judge import (
    _estimate_chat_cost_usd,
    is_transient_openai_error,
)

logger = logging.getLogger(__name__)


class RegressionCompareJudgeOutput(BaseModel):
    verdict: Literal["improved", "regressed", "unchanged"]
    score: float = Field(ge=-1.0, le=1.0)
    reasoning: str = Field(min_length=1, max_length=4000)

    @field_validator("verdict", mode="before")
    @classmethod
    def norm_verdict(cls, v: Any) -> str:
        s = str(v or "").strip().lower()
        if s in ("improved", "regressed", "unchanged"):
            return s
        if s in ("better", "improvement"):
            return "improved"
        if s in ("worse", "worsened", "degraded"):
            return "regressed"
        if s in ("same", "similar", "neutral", "no_change"):
            return "unchanged"
        return "unchanged"

    @field_validator("reasoning", mode="before")
    @classmethod
    def reasoning_str(cls, v: Any) -> str:
        if v is None:
            return "No reasoning provided."
        return str(v).strip() or "No reasoning provided."


@dataclass(frozen=True)
class RegressionCompareJudgeResult:
    output: RegressionCompareJudgeOutput
    raw_response: str
    cost_usd: float | None = None
    latency_ms: int | None = None


class RegressionCompareParseError(Exception):
    def __init__(self, message: str, *, raw_content: str | None, cause: Exception | None) -> None:
        super().__init__(message)
        self.raw_content = raw_content
        self.cause = cause


def build_regression_compare_prompt(
    *,
    user_query: str,
    context: str,
    previous_output: str,
    current_output: str,
) -> str:
    ctx = context.strip() if context.strip() else "(none)"
    return f"""You are an expert evaluator of AI system behavior.

Your task is to compare two outputs from the same system for the same input and determine if the newer output is better, worse, or unchanged relative to the older one.

Evaluate based on:
- correctness
- groundedness (if context is provided)
- relevance to the user query
- clarity and completeness

INPUT:
User Query:
{user_query}

Context (optional):
{ctx}

PREVIOUS OUTPUT:
{previous_output}

CURRENT OUTPUT:
{current_output}

---

Instructions:

1. Compare the CURRENT OUTPUT against the PREVIOUS OUTPUT.
2. Decide if the CURRENT OUTPUT is: improved, regressed, or unchanged versus the previous output.
3. Provide a score from -1.0 to 1.0:
   - 1.0 = clear improvement
   - 0.0 = no meaningful change
   - -1.0 = clear regression
4. Explain your reasoning briefly.

Return JSON ONLY with keys verdict, score, reasoning (no other keys, no markdown).
- verdict: one of improved, regressed, unchanged
- score: number from -1.0 to 1.0
- reasoning: short explanation
"""


def call_regression_compare_judge(
    *,
    user_query: str,
    context: str,
    previous_output: str,
    current_output: str,
    api_key: str | None = None,
) -> RegressionCompareJudgeResult:
    from openai import OpenAI

    resolved = (api_key or os.environ.get("OPENAI_API_KEY") or "").strip()
    if not resolved:
        raise RuntimeError("OPENAI_API_KEY is not set")

    model = os.environ.get("OPENAI_REGRESSION_MODEL") or os.environ.get("OPENAI_EVAL_MODEL", "gpt-4o-mini")
    prompt = build_regression_compare_prompt(
        user_query=user_query,
        context=context,
        previous_output=previous_output,
        current_output=current_output,
    )
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
                max_tokens=800,
                temperature=0.0,
            )
            latency_ms = int((time.perf_counter() - t0) * 1000)
            raw = (completion.choices[0].message.content or "").strip()
            last_raw = raw
            if not raw:
                raise ValueError("empty model content")
            out = RegressionCompareJudgeOutput.model_validate_json(raw)
            usage = completion.usage
            pt = int(getattr(usage, "prompt_tokens", None) or 0) if usage else 0
            ct = int(getattr(usage, "completion_tokens", None) or 0) if usage else 0
            cost = _estimate_chat_cost_usd(model=model, prompt_tokens=pt, completion_tokens=ct)
            return RegressionCompareJudgeResult(
                output=out, raw_response=raw, cost_usd=cost, latency_ms=latency_ms
            )
        except (json.JSONDecodeError, ValidationError, ValueError) as e:
            last_parse_err = e
            logger.warning(
                "regression compare judge parse attempt %s failed: %s raw_preview=%r",
                attempt + 1,
                e,
                (last_raw or "")[:400],
            )
        except Exception as e:
            if is_transient_openai_error(e):
                logger.warning("regression compare judge transient error (will retry job): %s", e)
                raise
            logger.warning("regression compare judge non-retryable error: %s", e)
            raise

    raise RegressionCompareParseError(
        f"Regression judge output invalid after retries: {last_parse_err}",
        raw_content=last_raw,
        cause=last_parse_err,
    )
