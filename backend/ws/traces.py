from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from typing import Any

from fastapi import WebSocket


class TraceWebSocketManager:
    def __init__(self) -> None:
        # tenant_id (or None for unauthenticated) → active connections
        self._rooms: dict[str | None, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket, tenant_id: str | None) -> None:
        await ws.accept()
        async with self._lock:
            self._rooms[tenant_id].add(ws)

    async def disconnect(self, ws: WebSocket, tenant_id: str | None) -> None:
        async with self._lock:
            self._rooms[tenant_id].discard(ws)
            if not self._rooms[tenant_id]:
                del self._rooms[tenant_id]

    async def broadcast(self, message: dict[str, Any], tenant_id: str | None) -> None:
        """Send message only to connections registered under tenant_id."""
        payload = json.dumps(message, default=str)
        async with self._lock:
            conns = list(self._rooms.get(tenant_id, set()))
        if not conns:
            return

        dead: list[WebSocket] = []
        for ws in conns:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)

        if dead:
            async with self._lock:
                for ws in dead:
                    self._rooms[tenant_id].discard(ws)


trace_ws_manager = TraceWebSocketManager()
