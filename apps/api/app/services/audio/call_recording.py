import asyncio
import logging
import time
from uuid import UUID

from app.core.database import AsyncSessionLocal
from app.models.call_session import CallLog
from app.services.audio.circular_audio_buffer import ContiguousVADBuffer, SAMPLE_RATE, NUM_CHANNELS, mix_and_encode_wav
from app.services.infra.storage import upload_call_recording

logger = logging.getLogger(__name__)


class CallRecorder:
    def __init__(self, room, org_id: UUID, call_id: UUID):
        self.room = room
        self.org_id = org_id
        self.call_id = call_id
        self.buffer = ContiguousVADBuffer(str(call_id), max_recording_sec=1800)
        self.started_at = time.monotonic()
        self.tasks = {}
        self.finalize_task = None
        self.capture_failed = False
        self.checkpoint_task = None

    def start(self):
        self.room.on("track_subscribed", self._remote_track)
        self.room.on("local_track_published", self._local_track)
        for participant in self.room.remote_participants.values():
            for publication in participant.track_publications.values():
                if publication.track:
                    self._remote_track(publication.track, publication, participant)
        for publication in self.room.local_participant.track_publications.values():
            self._local_track(publication, publication.track)
        self.checkpoint_task = asyncio.create_task(self._checkpoint_loop())

    async def _checkpoint_loop(self):
        while True:
            await asyncio.sleep(15)
            try:
                caller_bytes, remote_bytes = self.buffer.snapshot_buffers()
                wav = await asyncio.to_thread(mix_and_encode_wav, caller_bytes, remote_bytes)
                path = await asyncio.wait_for(upload_call_recording(self.org_id, self.call_id, wav, checkpoint=True), 12) if wav else None
                if path:
                    async with AsyncSessionLocal() as db:
                        call = await db.get(CallLog, self.call_id)
                        if call and call.org_id == self.org_id:
                            call.recording_storage_path = path
                            call.recording_status = "processing"
                            await db.commit()
            except Exception:
                logger.warning("Call recording checkpoint failed for %s", self.call_id)

    def _remote_track(self, track, publication, participant):
        self._capture(track, "remote" if participant.identity.startswith("staff_") else "caller")

    def _local_track(self, publication, track):
        if track:
            self._capture(track, "remote")

    def _capture(self, track, track_type):
        from livekit import rtc
        if track.kind != rtc.TrackKind.KIND_AUDIO or track.sid in self.tasks:
            return
        self.tasks[track.sid] = asyncio.create_task(self._consume(track, track_type))

    async def _consume(self, track, track_type):
        from livekit import rtc
        stream = rtc.AudioStream(track, sample_rate=SAMPLE_RATE, num_channels=NUM_CHANNELS)
        cursor = None
        try:
            async for event in stream:
                frame = event.frame
                if cursor is None:
                    cursor = max(0, time.monotonic() - self.started_at - frame.samples_per_channel / SAMPLE_RATE)
                self.buffer.push_frame(bytes(frame.data), track_type, offset_sec=cursor)
                cursor += frame.samples_per_channel / SAMPLE_RATE
        except asyncio.CancelledError:
            raise
        except Exception:
            self.capture_failed = True
            logger.exception("Call audio capture failed")
        finally:
            await stream.aclose()

    async def finalize(self):
        if self.finalize_task is None:
            self.finalize_task = asyncio.create_task(self._finalize())
        return await asyncio.shield(self.finalize_task)

    async def _finalize(self):
        if self.checkpoint_task:
            self.checkpoint_task.cancel()
            await asyncio.gather(self.checkpoint_task, return_exceptions=True)
        self.room.off("track_subscribed", self._remote_track)
        self.room.off("local_track_published", self._local_track)
        for task in self.tasks.values():
            task.cancel()
        outcomes = await asyncio.gather(*self.tasks.values(), return_exceptions=True)
        if any(isinstance(outcome, Exception) for outcome in outcomes):
            self.capture_failed = True
        try:
            async with AsyncSessionLocal() as db:
                call = await db.get(CallLog, self.call_id)
                if not call or call.org_id != self.org_id:
                    raise ValueError("Recording call tenant mismatch")
                call.recording_status = "processing"
                await db.commit()
            caller_bytes, remote_bytes = self.buffer.snapshot_buffers()
            wav = await asyncio.to_thread(mix_and_encode_wav, caller_bytes, remote_bytes)
            path = await asyncio.wait_for(upload_call_recording(self.org_id, self.call_id, wav), 12) if wav else None
            async with AsyncSessionLocal() as db:
                call = await db.get(CallLog, self.call_id)
                if not call or call.org_id != self.org_id:
                    raise ValueError("Recording call tenant mismatch")
                call.recording_status = ("ready" if not self.capture_failed else "partial") if path else "failed"
                call.recording_storage_path = path
                call.audio_recording_url = None
                await db.commit()
            return path
        except Exception:
            logger.exception("Call recording finalization failed")
            async with AsyncSessionLocal() as db:
                call = await db.get(CallLog, self.call_id)
                if call and call.org_id == self.org_id:
                    call.recording_status = "partial" if call.recording_storage_path else "failed"
                    await db.commit()
            raise
        finally:
            self.buffer.caller_buffer.clear()
            self.buffer.remote_buffer.clear()
