import json
import logging
import time
from datetime import datetime, timedelta
from typing import Optional, AsyncGenerator, Dict, Any, List
from uuid import UUID
from redis.asyncio import Redis, from_url
from app.core.config import settings
from app.schemas.patient import HotCacheEvaluationResult

logger = logging.getLogger(__name__)

TTL_LIVE_REDIAL = 1800
TTL_FOLLOWUP_48H = 172800
TTL_CHRONIC_MEDS = 86400


class DistributedRedisService:
    def __init__(self):
        self._redis: Optional[Redis] = None
        self._fallback_active = False
        self._in_memory_locks: Dict[str, tuple] = {}
        self._in_memory_channels: Dict[str, set] = {}

    async def get_client(self) -> Optional[Redis]:
        if self._fallback_active:
            return None
        if not settings.REDIS_URL:
            self._fallback_active = True
            return None
        if self._redis is None:
            try:
                client = from_url(
                    settings.REDIS_URL,
                    encoding="utf-8",
                    decode_responses=True,
                )
                await client.ping()
                self._redis = client
            except Exception as e:
                logger.warning(f"Redis fallback active: {e}")
                self._fallback_active = True
                self._redis = None
        return self._redis

    async def acquire_call_lock(
        self, room_name: str, staff_id: str, ttl_seconds: int = 300
    ) -> bool:
        client = await self.get_client()
        if client is None:
            lock_key = f"lock:call_accept:{room_name}"
            now = time.time()
            if lock_key in self._in_memory_locks:
                owner, expires = self._in_memory_locks[lock_key]
                if now < expires:
                    return owner == staff_id
            self._in_memory_locks[lock_key] = (staff_id, now + ttl_seconds)
            return True

        lock_key = f"lock:call_accept:{room_name}"
        acquired = await client.set(lock_key, staff_id, nx=True, ex=ttl_seconds)
        return bool(acquired)

    async def get_call_owner(self, room_name: str) -> Optional[str]:
        client = await self.get_client()
        if client is None:
            lock_key = f"lock:call_accept:{room_name}"
            if lock_key in self._in_memory_locks:
                owner, expires = self._in_memory_locks[lock_key]
                if time.time() < expires:
                    return owner
            return None

        lock_key = f"lock:call_accept:{room_name}"
        return await client.get(lock_key)

    async def release_call_lock(self, room_name: str) -> None:
        client = await self.get_client()
        if client is None:
            lock_key = f"lock:call_accept:{room_name}"
            self._in_memory_locks.pop(lock_key, None)
            return

        lock_key = f"lock:call_accept:{room_name}"
        await client.delete(lock_key)

    async def publish_org_event(self, org_id: str, message: dict) -> None:
        client = await self.get_client()
        if client is None:
            channel = f"org_channel:{org_id}"
            listeners = self._in_memory_channels.get(channel, set())
            for q in list(listeners):
                try:
                    q.put_nowait(message)
                except Exception:
                    pass
            return

        try:
            channel = f"org_channel:{org_id}"
            await client.publish(channel, json.dumps(message))
        except Exception as e:
            logger.warning(f"Redis publish fallback: {e}")

    async def subscribe_org_channel(self, org_id: str) -> AsyncGenerator[dict, None]:
        client = await self.get_client()
        if client is None:
            import asyncio

            channel = f"org_channel:{org_id}"
            q = asyncio.Queue()
            if channel not in self._in_memory_channels:
                self._in_memory_channels[channel] = set()
            self._in_memory_channels[channel].add(q)
            try:
                while True:
                    msg = await q.get()
                    yield msg
            finally:
                self._in_memory_channels[channel].discard(q)
            return

        pubsub = client.pubsub()
        channel = f"org_channel:{org_id}"
        await pubsub.subscribe(channel)
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        yield data
                    except Exception:
                        pass
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()

    async def get_clinic_config(self, org_id: str) -> Optional[Dict[str, Any]]:
        client = await self.get_client()
        if client is None:
            return None
        raw = await client.get(f"clinic:config:{org_id}")
        if raw:
            try:
                return json.loads(raw)
            except Exception:
                return None
        return None

    async def set_clinic_config(
        self, org_id: str, config: Dict[str, Any], ttl: int = 3600
    ) -> None:
        client = await self.get_client()
        if client is None:
            return
        await client.set(f"clinic:config:{org_id}", json.dumps(config), ex=ttl)

    async def invalidate_clinic_config(self, org_id: str) -> None:
        client = await self.get_client()
        if client is None:
            return
        await client.delete(f"clinic:config:{org_id}")


class PhoneHotCacheService:
    def __init__(self):
        self._local_cache: Dict[str, Dict[str, Any]] = {}

    def _build_cache_key(self, org_id: UUID, e164_phone: str) -> str:
        clean_phone = e164_phone.strip().replace(" ", "")
        return f"org:{str(org_id)}:phone:{clean_phone}"

    async def evaluate_hot_cache_promotion(
        self,
        org_id: UUID,
        e164_phone: str,
        recent_appointment_at: Optional[datetime] = None,
        has_active_medication: bool = False,
        is_live_call: bool = True,
    ) -> HotCacheEvaluationResult:
        now = datetime.utcnow()

        if recent_appointment_at:
            delta = abs(now - recent_appointment_at)
            if delta <= timedelta(hours=48):
                return HotCacheEvaluationResult(
                    phone_number=e164_phone,
                    org_id=org_id,
                    should_cache=True,
                    cache_ttl_seconds=TTL_FOLLOWUP_48H,
                    promotion_reason="FOLLOWUP_48H",
                )

        if has_active_medication:
            return HotCacheEvaluationResult(
                phone_number=e164_phone,
                org_id=org_id,
                should_cache=True,
                cache_ttl_seconds=TTL_CHRONIC_MEDS,
                promotion_reason="CHRONIC_MEDICATION",
            )

        if is_live_call:
            return HotCacheEvaluationResult(
                phone_number=e164_phone,
                org_id=org_id,
                should_cache=True,
                cache_ttl_seconds=TTL_LIVE_REDIAL,
                promotion_reason="ACTIVE_REDIAL",
            )

        return HotCacheEvaluationResult(
            phone_number=e164_phone,
            org_id=org_id,
            should_cache=False,
            cache_ttl_seconds=0,
            promotion_reason="DORMANT_RECORD",
        )

    async def cache_patient_profile(
        self,
        org_id: UUID,
        e164_phone: str,
        patient_data: Dict[str, Any],
        ttl_seconds: int = TTL_LIVE_REDIAL,
    ) -> bool:
        cache_key = self._build_cache_key(org_id, e164_phone)
        expire_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)

        payload = {
            "org_id": str(org_id),
            "phone_number": e164_phone,
            "profile": patient_data,
            "expires_at": expire_at.isoformat(),
        }

        self._local_cache[cache_key] = payload
        return True

    async def get_cached_patient_profile(
        self,
        org_id: UUID,
        e164_phone: str,
    ) -> Optional[Dict[str, Any]]:
        cache_key = self._build_cache_key(org_id, e164_phone)
        entry = self._local_cache.get(cache_key)

        if not entry:
            return None

        expires_at = datetime.fromisoformat(entry["expires_at"])
        if datetime.utcnow() > expires_at:
            del self._local_cache[cache_key]
            return None

        return entry["profile"]


class EphemeralPresenceService:
    def __init__(self, timeout_sec: int = 20):
        self.timeout_sec = timeout_sec
        self._presence_scores: Dict[str, Dict[str, Dict[str, Any]]] = {}

    def record_heartbeat(
        self, org_id: str, staff_id: str, role: str = "receptionist"
    ) -> None:
        if org_id not in self._presence_scores:
            self._presence_scores[org_id] = {}

        current = self._presence_scores[org_id].get(staff_id, {})
        status = current.get("status", "AVAILABLE")
        room_name = current.get("active_room", None)

        self._presence_scores[org_id][staff_id] = {
            "last_seen": time.time(),
            "status": status,
            "role": role,
            "active_room": room_name,
        }

    def set_staff_busy(self, org_id: str, staff_id: str, room_name: str) -> None:
        if org_id not in self._presence_scores:
            self._presence_scores[org_id] = {}

        entry = self._presence_scores[org_id].get(
            staff_id, {"last_seen": time.time(), "role": "receptionist"}
        )
        entry["status"] = "BUSY"
        entry["active_room"] = room_name
        entry["last_seen"] = time.time()
        self._presence_scores[org_id][staff_id] = entry

    def set_staff_available(
        self, org_id: str, staff_id: str, role: str = "receptionist"
    ) -> None:
        if org_id not in self._presence_scores:
            self._presence_scores[org_id] = {}
        if staff_id not in self._presence_scores[org_id]:
            self._presence_scores[org_id][staff_id] = {
                "last_seen": time.time(),
                "role": role,
            }
        self._presence_scores[org_id][staff_id]["status"] = "AVAILABLE"
        self._presence_scores[org_id][staff_id]["active_room"] = None
        self._presence_scores[org_id][staff_id]["last_seen"] = time.time()

    def get_staff_status(self, org_id: str, staff_id: str) -> str:
        if (
            org_id in self._presence_scores
            and staff_id in self._presence_scores[org_id]
        ):
            return self._presence_scores[org_id][staff_id].get("status", "OFFLINE")
        return "OFFLINE"

    def get_available_dispatchers(self, org_id: str) -> List[str]:
        if org_id not in self._presence_scores:
            return []

        now = time.time()
        alive_free_staff = []
        expired = []

        for staff_id, data in self._presence_scores[org_id].items():
            if now - data["last_seen"] <= self.timeout_sec:
                if data.get("status") == "AVAILABLE":
                    alive_free_staff.append(staff_id)
            else:
                expired.append(staff_id)

        for staff_id in expired:
            self._presence_scores[org_id].pop(staff_id, None)

        return alive_free_staff

    def get_available_staff(self, org_id: str) -> List[str]:
        return self.get_available_dispatchers(org_id)

    def get_first_available_staff(self, org_id: str) -> Optional[Dict[str, Any]]:
        free_ids = self.get_available_dispatchers(org_id)
        if not free_ids:
            return None
        staff_id = free_ids[0]
        data = self._presence_scores[org_id][staff_id]
        return {
            "staff_id": staff_id,
            "role": data.get("role", "receptionist"),
            "status": data.get("status", "AVAILABLE"),
        }

    def is_dispatcher_online(self, org_id: str) -> bool:
        return len(self.get_available_dispatchers(org_id)) > 0

    def is_staff_online(self, org_id: str) -> bool:
        return self.is_dispatcher_online(org_id)

    def remove_dispatcher(self, org_id: str, dispatcher_id: str) -> None:
        if org_id in self._presence_scores:
            self._presence_scores[org_id].pop(dispatcher_id, None)

    def remove_staff(self, org_id: str, staff_id: str) -> None:
        self.remove_dispatcher(org_id, staff_id)


PresenceService = EphemeralPresenceService
presence_service = EphemeralPresenceService()
distributed_redis = DistributedRedisService()
redis_service = distributed_redis
phone_hot_cache = PhoneHotCacheService()
hot_cache_service = phone_hot_cache

_slot_cache: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS = 30


def _build_slot_cache_key(
    org_id: str, target_date: str, specialty: Optional[str] = None
) -> str:
    spec_key = (specialty or "ALL").strip().lower()
    return f"org:{org_id}:date:{target_date}:spec:{spec_key}"


def get_cached_slots(
    org_id: str, target_date: str, specialty: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    key = _build_slot_cache_key(org_id, target_date, specialty)
    entry = _slot_cache.get(key)
    if not entry:
        return None

    if time.time() - entry.get("created_at", 0) > CACHE_TTL_SECONDS:
        _slot_cache.pop(key, None)
        return None

    return entry.get("data")


def set_cached_slots(
    org_id: str, target_date: str, data: Dict[str, Any], specialty: Optional[str] = None
) -> None:
    key = _build_slot_cache_key(org_id, target_date, specialty)
    _slot_cache[key] = {"data": data, "created_at": time.time()}


def invalidate_slot_cache(org_id: str, target_date: str) -> None:
    prefix = f"org:{org_id}:date:{target_date}:"
    keys_to_del = [k for k in _slot_cache if k.startswith(prefix)]
    for k in keys_to_del:
        _slot_cache.pop(k, None)

