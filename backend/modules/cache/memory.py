from __future__ import annotations

from typing import Any


class InMemoryCache:
    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def get(self, key: str) -> Any | None:
        return self._data.get(key)

    def set(self, key: str, value: Any, ttl_s: int | None = None) -> None:
        _ = ttl_s
        self._data[key] = value

    def delete(self, key: str) -> None:
        self._data.pop(key, None)
