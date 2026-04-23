"""Shared pytest fixtures for the entire test suite.

Fixtures defined here are automatically available to every test file without
any explicit import.  pytest discovers this file by its standard name.

Reading guide
-------------
fresh_cache   — gives each test an isolated, empty InMemoryCache and
                resets the module-level singleton so no state leaks between
                test cases.  Marked autouse=True so it runs for every test.

test_client   — a Starlette TestClient wrapping the FastAPI app.  Uses
                fresh_cache (already autouse) so route handlers see the same
                empty cache that the test is about to manipulate.
"""

from __future__ import annotations

import pytest

import modules.cache as cache_module
from modules.cache.memory import InMemoryCache


@pytest.fixture(autouse=True)
def fresh_cache(monkeypatch: pytest.MonkeyPatch) -> InMemoryCache:
    """Replace the cache singleton with a fresh InMemoryCache before every test.

    Why monkeypatch instead of just calling _reset_cache()?
    --------------------------------------------------------
    ``_reset_cache()`` sets ``_cache_instance = None``, which means the *next*
    call to ``get_cache()`` triggers ``_build_cache()``.  If ``CACHE_BACKEND``
    happens to be set to "redis" in the test environment, we'd get a RedisCache
    pointing at a real Redis.  That makes tests non-deterministic and slow.

    Instead, we monkeypatch ``_cache_instance`` directly with a known good
    InMemoryCache.  This bypasses ``_build_cache()`` entirely, so tests are
    always fast and isolated regardless of env vars.

    The monkeypatch is automatically reverted after each test, so the real
    singleton is restored for any non-test code that runs afterward.
    """
    cache = InMemoryCache()
    monkeypatch.setattr(cache_module, "_cache_instance", cache)
    return cache


@pytest.fixture
def test_client(fresh_cache: InMemoryCache):  # noqa: F811  (fresh_cache is autouse anyway)
    """A Starlette TestClient for the FastAPI app.

    The fresh_cache fixture is already autouse, but listing it as an explicit
    argument here documents the dependency clearly: route handlers will see
    the same isolated InMemoryCache that the test manipulates.
    """
    from fastapi.testclient import TestClient
    from main import app

    with TestClient(app) as client:
        yield client
