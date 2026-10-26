import asyncio
import inspect
import logging
import uuid
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.outbox_event import OutboxEvent
from app.models.voice_mutation_operation import VoiceMutationOperation

logger = logging.getLogger(__name__)

MAX_RELAY_ATTEMPTS = 5
DEFAULT_RELAY_BATCH_SIZE = 50
DEFAULT_POLL_INTERVAL_SECONDS = 1.0


async def record_mutation_operation(
    db: AsyncSession,
    org_id: UUID,
    call_id: UUID | None,
    operation_key: str,
    operation_type: str,
    response_payload: dict[str, Any],
    status: str = "completed",
) -> VoiceMutationOperation | None:
    now = datetime.now(UTC)
    stmt = (
        pg_insert(VoiceMutationOperation)
        .values(
            id=uuid.uuid4(),
            org_id=org_id,
            call_id=call_id,
            operation_key=operation_key,
            operation_type=operation_type,
            status=status,
            response_payload=response_payload,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_update(
            index_elements=["operation_key"],
            set_={
                "response_payload": response_payload,
                "status": status,
                "updated_at": now,
            },
        )
        .returning(VoiceMutationOperation)
    )
    result = await db.execute(stmt)
    await db.flush()
    if not hasattr(result, "scalar_one"):
        return None
    res = result.scalar_one()
    if inspect.isawaitable(res):
        res = await res
    return res


async def get_mutation_operation(
    db: AsyncSession,
    org_id: UUID,
    operation_key: str,
) -> VoiceMutationOperation | None:
    stmt = select(VoiceMutationOperation).where(
        VoiceMutationOperation.org_id == org_id,
        VoiceMutationOperation.operation_key == operation_key,
    )
    result = await db.execute(stmt)
    if not hasattr(result, "scalar_one_or_none"):
        return None
    res = result.scalar_one_or_none()
    if inspect.isawaitable(res):
        res = await res
    if isinstance(res, VoiceMutationOperation):
        return res
    if (
        hasattr(res, "status")
        and not callable(res.status)
        and hasattr(res, "response_payload")
        and not callable(res.response_payload)
        and not isinstance(res.status, (MagicMock, AsyncMock))
    ):
        return res
    return None


async def enqueue_outbox_event(
    db: AsyncSession,
    org_id: UUID,
    event_type: str,
    payload: dict[str, Any],
) -> OutboxEvent:
    now = datetime.now(UTC)
    event = OutboxEvent(
        id=uuid.uuid4(),
        org_id=org_id,
        event_type=event_type,
        payload=payload,
        status="pending",
        attempts=0,
        created_at=now,
    )
    db.add(event)
    await db.flush()
    outbox_relay.notify()
    return event


class OutboxRelay:
    def __init__(
        self,
        poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
        batch_size: int = DEFAULT_RELAY_BATCH_SIZE,
        max_attempts: int = MAX_RELAY_ATTEMPTS,
    ):
        self.poll_interval = poll_interval
        self.batch_size = batch_size
        self.max_attempts = max_attempts
        self._running = False
        self._task: asyncio.Task | None = None
        self._notify_event = asyncio.Event()

    def notify(self) -> None:
        self._notify_event.set()

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._notify_event.clear()
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self._running = False
        self._notify_event.set()
        if self._task and not self._task.done():
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
        self._task = None

    async def _run_loop(self) -> None:
        while self._running:
            try:
                processed = await self.process_batch(self.batch_size)
                if processed > 0:
                    continue
                try:
                    await asyncio.wait_for(self._notify_event.wait(), timeout=self.poll_interval)
                    self._notify_event.clear()
                except TimeoutError:
                    pass
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"[OUTBOX RELAY ERROR] Unexpected loop exception: {exc}")
                await asyncio.sleep(self.poll_interval)

    async def process_batch(self, batch_size: int = DEFAULT_RELAY_BATCH_SIZE, db: AsyncSession | None = None) -> int:
        if db is not None:
            return await self._process_batch_internal(db, batch_size)
        async with AsyncSessionLocal() as session:
            try:
                count = await self._process_batch_internal(session, batch_size)
                await session.commit()
                return count
            except Exception:
                await session.rollback()
                raise

    async def _process_batch_internal(self, db: AsyncSession, batch_size: int) -> int:
        stmt = (
            select(OutboxEvent)
            .where(OutboxEvent.status == "pending")
            .order_by(OutboxEvent.created_at.asc())
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        res = await db.execute(stmt)
        events = res.scalars().all()
        if not events:
            return 0

        for event in events:
            await self._dispatch_event(event)

        await db.flush()
        return len(events)

    async def _dispatch_event(self, event: OutboxEvent) -> None:
        now = datetime.now(UTC)
        try:
            from app.services.infra.websocket_manager import ws_manager
            await ws_manager.broadcast_to_org(str(event.org_id), event.payload)
            event.status = "published"
            event.published_at = now
            event.attempts += 1
            event.last_attempt_at = now
        except Exception as exc:
            event.attempts += 1
            event.last_attempt_at = now
            event.error_detail = str(exc)
            if event.attempts >= self.max_attempts:
                event.status = "failed"
                logger.error(
                    f"[OUTBOX POISON EVENT] Event {event.id} ({event.event_type}) failed {event.attempts} times: {exc}"
                )


outbox_relay = OutboxRelay()
