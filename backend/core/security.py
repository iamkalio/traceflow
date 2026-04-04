"""API keys and auth-related helpers."""

from __future__ import annotations

from fastapi import HTTPException


def validate_openai_api_key(api_key: str) -> None:
    """Validate an OpenAI API key with a lightweight API call."""
    if not api_key or not api_key.strip():
        raise HTTPException(status_code=400, detail="api_key is empty")
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key.strip())
        client.models.list()
    except Exception as e:
        msg = str(e)
        if len(msg) > 500:
            msg = msg[:500] + "…"
        raise HTTPException(status_code=400, detail=f"Invalid OpenAI API key: {msg}") from e
