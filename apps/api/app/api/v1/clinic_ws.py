import asyncio
import json
from uuid import UUID
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from app.services.infra.websocket_manager import ws_manager
from app.services.infra.redis_cache import presence_service
from app.core.security import get_supabase_admin_client
from app.core.database import AsyncSessionLocal
from app.models.user import User
from app.models.clinic_membership import ClinicMembership
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

router = APIRouter()


async def authenticate_websocket(websocket: WebSocket, org_id: str, token: Optional[str]) -> Optional[User]:
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None

    client = get_supabase_admin_client()
    if not client:
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        return None

    try:
        auth_res = await run_in_threadpool(client.auth.get_user, token)
        if not auth_res or not auth_res.user:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return None
    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None

    try:
        user_uuid = UUID(str(auth_res.user.id))
        target_org_uuid = UUID(org_id)
    except (ValueError, TypeError):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None

    async with AsyncSessionLocal() as session:
        user_record = await session.get(User, user_uuid)
        if not user_record or not user_record.is_active:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return None
        membership = await session.scalar(select(ClinicMembership).where(
            ClinicMembership.user_id == user_uuid, ClinicMembership.org_id == target_org_uuid,
            ClinicMembership.status == "active",
        ))
        if not membership:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return None

    return user_record


@router.websocket("/ws/clinic/{org_id}")
@router.websocket("/ws/dispatch/{org_id}")
async def clinic_websocket(
    websocket: WebSocket,
    org_id: str,
):
    await websocket.accept()
    try:
        auth_message = await asyncio.wait_for(websocket.receive_text(), timeout=5)
        if len(auth_message) > 16384:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        auth_payload = json.loads(auth_message)
        token = auth_payload.get("token") if isinstance(auth_payload, dict) and auth_payload.get("type") == "auth" else None
        if not isinstance(token, str):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    except WebSocketDisconnect:
        return
    except (asyncio.TimeoutError, ValueError):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    user = await authenticate_websocket(websocket, org_id, token)
    if not user:
        return

    await ws_manager.connect(websocket, org_id)
    try:
        while True:
            data_raw = await websocket.receive_text()
            if not data_raw:
                continue
            try:
                data = json.loads(data_raw)
                if isinstance(data, dict) and data.get("type") in ("ping", "heartbeat"):
                    presence_service.record_heartbeat(org_id, str(user.id))
                    await websocket.send_json({"type": "pong", "status": "active"})
            except Exception:
                pass
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, org_id)
    except Exception:
        ws_manager.disconnect(websocket, org_id)
