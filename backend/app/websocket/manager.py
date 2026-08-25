"""
Broadcasts deployment progress events to connected clients, keyed by
deployment_id, so a frontend can stream "bootstrapping ephemeral node...",
"waiting for BMH available...", "control plane ready...", etc. in real time.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, deployment_id: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections[deployment_id].add(ws)

    async def disconnect(self, deployment_id: str, ws: WebSocket) -> None:
        async with self._lock:
            self._connections[deployment_id].discard(ws)

    async def broadcast(self, deployment_id: str, event: dict) -> None:
        dead = []
        for ws in list(self._connections.get(deployment_id, [])):
            try:
                await ws.send_text(json.dumps(event))
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(deployment_id, ws)


manager = ConnectionManager()
