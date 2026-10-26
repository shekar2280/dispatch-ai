import asyncio
import json
import logging
import uuid
from collections import deque
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.call_turn import VoiceCallTurn
from app.services.infra.redis_cache import redis_service

logger = logging.getLogger(__name__)

STREAM_NAME = "voice:turns:journal"
CONSUMER_GROUP = "voice:turns:group"
STREAM_MAXLEN = 10000
MAX_BUFFER_ITEMS = 1000
MAX_BUFFER_BYTES = 5 * 1024 * 1024


@dataclass
class JournalTurnEvent:
    event_id: str
    session_id: str
    org_id: str
    turn_number: int
    is_critical: bool
    user_transcript: str | None = None
    user_audio_url: str | None = None
    ai_filler_text: str | None = None
    ai_filler_audio_url: str | None = None
    ai_response_text: str | None = None
    ai_response_audio_url: str | None = None
    stt_latency_ms: int | None = None
    llm_latency_ms: int | None = None
    tts_latency_ms: int | None = None
    total_latency_ms: int | None = None
    interrupted: bool = False
    created_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JournalTurnEvent":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class BoundedTurnJournalQueue:
    def __init__(self, maxsize: int = MAX_BUFFER_ITEMS, max_bytes: int = MAX_BUFFER_BYTES):
        self.maxsize = maxsize
        self.max_bytes = max_bytes
        self._items: deque[Any] = deque()
        self.current_bytes = 0
        self.shed_count = 0

    def qsize(self) -> int:
        return len(self._items)

    def empty(self) -> bool:
        return len(self._items) == 0

    def full(self) -> bool:
        return len(self._items) >= self.maxsize or self.current_bytes >= self.max_bytes

    def _estimate_size(self, item: Any) -> int:
        base = 256
        for attr in ("user_transcript", "ai_response_text", "ai_filler_text", "event_id"):
            val = getattr(item, attr, None)
            if isinstance(val, str):
                base += len(val.encode("utf-8"))
        return base

    def put_nowait(self, item: Any) -> bool:
        item_bytes = self._estimate_size(item)
        is_critical = bool(
            getattr(item, "user_transcript", None) or getattr(item, "ai_response_text", None)
        )

        while (len(self._items) >= self.maxsize or self.current_bytes + item_bytes > self.max_bytes) and len(self._items) > 0:
            if is_critical:
                evicted_idx = None
                for idx, existing in enumerate(self._items):
                    if not (getattr(existing, "user_transcript", None) or getattr(existing, "ai_response_text", None)):
                        evicted_idx = idx
                        break
                if evicted_idx is not None:
                    evicted = self._items[evicted_idx]
                    del self._items[evicted_idx]
                    self.current_bytes -= self._estimate_size(evicted)
                    self.shed_count += 1
                else:
                    evicted = self._items.popleft()
                    self.current_bytes -= self._estimate_size(evicted)
                    self.shed_count += 1
            else:
                self.shed_count += 1
                return False

        self._items.append(item)
        self.current_bytes += item_bytes
        return True

    def get_nowait(self) -> Any:
        if not self._items:
            raise asyncio.QueueEmpty()
        item = self._items.popleft()
        self.current_bytes = max(0, self.current_bytes - self._estimate_size(item))
        return item

    def clear(self):
        self._items.clear()
        self.current_bytes = 0


class EventJournal:
    def __init__(self):
        self.consumer_name = f"worker:{uuid.uuid4().hex[:8]}"
        self.is_running = False
        self._task: asyncio.Task | None = None

    async def publish_turn(self, event: JournalTurnEvent) -> bool:
        try:
            client = await redis_service.get_client()
            if client is not None:
                payload = json.dumps(event.to_dict())
                await client.xadd(STREAM_NAME, {"payload": payload}, maxlen=STREAM_MAXLEN, approximate=True)
                return True
        except Exception as exc:
            logger.warning("Failed publishing turn to Redis Stream: %s", exc)
        return False

    async def ensure_consumer_group(self):
        client = await redis_service.get_client()
        if client is None:
            return
        try:
            await client.xgroup_create(STREAM_NAME, CONSUMER_GROUP, id="0", mkstream=True)
        except Exception as exc:
            if "BUSYGROUP" not in str(exc):
                logger.warning("Consumer group setup check: %s", exc)

    async def process_batch(self, batch_size: int = 50) -> int:
        client = await redis_service.get_client()
        if client is None:
            return 0

        try:
            entries = await client.xreadgroup(
                CONSUMER_GROUP,
                self.consumer_name,
                {STREAM_NAME: ">"},
                count=batch_size,
                block=500,
            )
        except Exception as exc:
            logger.warning("Error reading from Redis turn stream: %s", exc)
            return 0

        if not entries:
            return 0

        stream_records = entries[0][1] if entries else []
        if not stream_records:
            return 0

        from app.core.database import AsyncSessionLocal

        valid_rows = []
        ack_ids = []

        for msg_id, data in stream_records:
            ack_ids.append(msg_id)
            try:
                raw_payload = data.get("payload")
                if not raw_payload:
                    continue
                parsed = json.loads(raw_payload) if isinstance(raw_payload, str) else raw_payload
                turn_event = JournalTurnEvent.from_dict(parsed)

                created_dt = (
                    datetime.fromisoformat(turn_event.created_at)
                    if turn_event.created_at
                    else datetime.now(UTC)
                )

                valid_rows.append(
                    {
                        "id": uuid.uuid4(),
                        "session_id": UUID(turn_event.session_id),
                        "org_id": UUID(turn_event.org_id),
                        "turn_number": turn_event.turn_number,
                        "event_id": turn_event.event_id,
                        "interrupted": turn_event.interrupted,
                        "user_transcript": turn_event.user_transcript,
                        "user_audio_url": turn_event.user_audio_url,
                        "ai_filler_text": turn_event.ai_filler_text,
                        "ai_filler_audio_url": turn_event.ai_filler_audio_url,
                        "ai_response_text": turn_event.ai_response_text,
                        "ai_response_audio_url": turn_event.ai_response_audio_url,
                        "stt_latency_ms": turn_event.stt_latency_ms,
                        "llm_latency_ms": turn_event.llm_latency_ms,
                        "tts_latency_ms": turn_event.tts_latency_ms,
                        "total_latency_ms": turn_event.total_latency_ms,
                        "created_at": created_dt,
                    }
                )
            except Exception as exc:
                logger.error("Skipping poison message in turn journal: %s", exc)

        if valid_rows:
            stmt = pg_insert(VoiceCallTurn).values(valid_rows).on_conflict_do_nothing()
            try:
                async with AsyncSessionLocal() as db:
                    await db.execute(stmt)
                    await db.commit()
            except Exception as exc:
                logger.error("Failed persisting turn batch to database: %s", exc)
                return 0

        if ack_ids:
            try:
                await client.xack(STREAM_NAME, CONSUMER_GROUP, *ack_ids)
            except Exception as exc:
                logger.warning("Failed acknowledging turn stream messages: %s", exc)

        return len(valid_rows)

    async def _consumer_loop(self):
        await self.ensure_consumer_group()
        while self.is_running:
            try:
                count = await self.process_batch(batch_size=50)
                if count == 0:
                    await asyncio.sleep(0.5)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Unexpected error in event journal loop: %s", exc)
                await asyncio.sleep(1.0)

    async def start(self):
        if self._task is None or self._task.done():
            self.is_running = True
            self._task = asyncio.create_task(self._consumer_loop())

    async def stop(self):
        self.is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None


event_journal = EventJournal()
