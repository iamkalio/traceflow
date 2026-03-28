"""OpenAI key validation (models.list)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from services.openai_key_validate import validate_openai_api_key


def test_validate_calls_models_list() -> None:
    with patch("openai.OpenAI") as m_cls:
        client = MagicMock()
        m_cls.return_value = client
        validate_openai_api_key("sk-good")
    m_cls.assert_called_once_with(api_key="sk-good")
    client.models.list.assert_called_once()


def test_validate_empty_key() -> None:
    with pytest.raises(HTTPException) as ei:
        validate_openai_api_key("")
    assert ei.value.status_code == 400


def test_validate_openai_error_maps_to_400() -> None:
    with patch("openai.OpenAI") as m_cls:
        m_cls.side_effect = ValueError("bad")
        with pytest.raises(HTTPException) as ei:
            validate_openai_api_key("sk-bad")
    assert ei.value.status_code == 400
    assert "Invalid" in (ei.value.detail or "")
