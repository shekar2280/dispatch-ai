import asyncio
import json
import logging
from typing import Dict, Set
from fastapi import WebSocket
from app.services.infra.redis_cache import redis_service

logger = logging.getLogger(__name__)


class DispatchWebSocketManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self.subscriber_tasks: Dict[str, asyncio.Task] = {}
        self.last_sos_alert: Dict[str, dict] = {}

    def _clean_org(self, org_id: str) -> str:
        return str(org_id or "").strip().lower()

    async def connect(self, websocket: WebSocket, org_id: str):
        clean_id = self._clean_org(org_id)
        if clean_id not in self.active_connections:
            self.active_connections[clean_id] = set()
        self.active_connections[clean_id].add(websocket)

        if clean_id not in self.subscriber_tasks or self.subscriber_tasks[clean_id].done():
            self.subscriber_tasks[clean_id] = asyncio.create_task(
                self._listen_redis_channel(clean_id)
            )

        if clean_id in self.last_sos_alert:
            try:
                await websocket.send_json(self.last_sos_alert[clean_id])
            except Exception:
                pass

    def disconnect(self, websocket: WebSocket, org_id: str):
        clean_id = self._clean_org(org_id)
        if clean_id in self.active_connections:
            self.active_connections[clean_id].discard(websocket)
            if not self.active_connections[clean_id]:
                del self.active_connections[clean_id]
                task = self.subscriber_tasks.pop(clean_id, None)
                if task and not task.done():
                    task.cancel()

    async def _listen_redis_channel(self, org_id: str):
        clean_id = self._clean_org(org_id)
        try:
            async for message in redis_service.subscribe_org_channel(clean_id):
                await self._broadcast_local(clean_id, message)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Redis sub error for org {clean_id}: {e}")

    async def _broadcast_local(self, org_id: str, message: dict):
        clean_id = self._clean_org(org_id)
        if message.get("event") in ("EMERGENCY_SOS_ALERT", "LIVE_EMERGENCY_INTAKE_UPDATED"):
            self.last_sos_alert[clean_id] = message

        target_sockets = set()
        if clean_id in self.active_connections:
            target_sockets.update(self.active_connections[clean_id])

        if not target_sockets:
            return

        dead_sockets = set()
        for connection in target_sockets:
            try:
                await connection.send_json(message)
            except Exception:
                dead_sockets.add(connection)

        for dead in dead_sockets:
            self.disconnect(dead, clean_id)

    async def broadcast_to_org(self, org_id: str, message: dict):
        clean_id = self._clean_org(org_id)
        await redis_service.publish_org_event(clean_id, message)
        await self._broadcast_local(clean_id, message)


ws_manager = DispatchWebSocketManager()
manager = ws_manager


async def broadcast_sos_alert(org_id: str, alert_data: dict):
    await ws_manager.broadcast_to_org(org_id, alert_data)
