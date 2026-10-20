import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
import pytest
from app.services.infra.websocket_manager import DispatchWebSocketManager


@pytest.mark.asyncio
async def test_websocket_multi_client_queue_sync():
    manager = DispatchWebSocketManager()
    org_id = str(uuid4())

    client1 = MagicMock()
    client1.send_json = AsyncMock()
    client2 = MagicMock()
    client2.send_json = AsyncMock()
    client3 = MagicMock()
    client3.send_json = AsyncMock()

    await manager.connect(client1, org_id)
    await manager.connect(client2, org_id)
    await manager.connect(client3, org_id)

    assert len(manager.active_connections[manager._clean_org(org_id)]) == 3

    event = {
        "event": "QUEUE_STATE_UPDATED",
        "appointment_id": str(uuid4()),
        "display_token": "W-5",
        "queue_state": "called",
    }

    await manager._broadcast_local(org_id, event)

    assert client1.send_json.await_count == 1
    assert client2.send_json.await_count == 1
    assert client3.send_json.await_count == 1

    assert client1.send_json.await_args.args[0] == event
    assert client2.send_json.await_args.args[0] == event
    assert client3.send_json.await_args.args[0] == event


@pytest.mark.asyncio
async def test_websocket_multi_tenant_isolation():
    manager = DispatchWebSocketManager()
    org_a = str(uuid4())
    org_b = str(uuid4())

    client_a = MagicMock()
    client_a.send_json = AsyncMock()
    client_b = MagicMock()
    client_b.send_json = AsyncMock()

    await manager.connect(client_a, org_a)
    await manager.connect(client_b, org_b)

    event_a = {
        "event": "PATIENT_INTAKE_ADMITTED",
        "org_id": org_a,
        "token": "W-1",
    }

    await manager._broadcast_local(org_a, event_a)

    assert client_a.send_json.await_count == 1
    assert client_b.send_json.await_count == 0


@pytest.mark.asyncio
async def test_websocket_dead_socket_pruning_and_sos_replay():
    manager = DispatchWebSocketManager()
    org_id = str(uuid4())

    healthy_client = MagicMock()
    healthy_client.send_json = AsyncMock()
    dead_client = MagicMock()
    dead_client.send_json = AsyncMock(side_effect=RuntimeError("Socket disconnected"))

    await manager.connect(healthy_client, org_id)
    await manager.connect(dead_client, org_id)

    sos_event = {
        "event": "EMERGENCY_SOS_ALERT",
        "chief_complaint": "Acute respiratory distress",
        "triage_status": "emergency",
    }

    await manager._broadcast_local(org_id, sos_event)

    assert healthy_client.send_json.await_count == 1
    assert dead_client.send_json.await_count == 1

    clean_org = manager._clean_org(org_id)
    assert dead_client not in manager.active_connections[clean_org]
    assert healthy_client in manager.active_connections[clean_org]

    late_client = MagicMock()
    late_client.send_json = AsyncMock()
    await manager.connect(late_client, org_id)

    assert late_client.send_json.await_count == 1
    assert late_client.send_json.await_args.args[0] == sos_event
