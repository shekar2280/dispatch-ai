import asyncio
import logging
import time
from uuid import UUID

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.call_session import CallLog
from app.models.voice_recording_chunk import VoiceRecordingChunk
from app.services.audio.circular_audio_buffer import (
    NUM_CHANNELS,
    SAMPLE_RATE,
    ChunkedAudioBuffer,
    stitch_wav_chunks,
)
from app.services.infra.storage import (
    download_call_recording_chunk,
    upload_call_recording,
    upload_call_recording_chunk,
)

logger = logging.getLogger(__name__)


class CallRecorder:
    def __init__(self, room, org_id: UUID, call_id: UUID, chunk_duration_sec: float = 30.0):
        self.room = room
        self.org_id = org_id
        self.call_id = call_id
        self.chunk_duration_sec = chunk_duration_sec
        self.buffer = ChunkedAudioBuffer(str(call_id), chunk_duration_sec=chunk_duration_sec)
        self.started_at = time.monotonic()
        self.tasks = {}
        self.finalize_task = None
        self.capture_failed = False
        self.checkpoint_task = None
        self.recorded_chunks = []

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
            await asyncio.sleep(5)
            try:
                while self.buffer.ready_chunk():
                    chunk_data = self.buffer.pop_chunk(force=False)
                    if not chunk_data:
                        break
                    wav_bytes, chunk_idx, offset_sec, duration_sec = chunk_data
                    path = await asyncio.wait_for(
                        upload_call_recording_chunk(self.org_id, self.call_id, chunk_idx, wav_bytes),
                        12,
                    )
                    self.recorded_chunks.append({
                        "chunk_index": chunk_idx,
                        "storage_path": path,
                        "duration_seconds": duration_sec,
                        "offset_seconds": offset_sec,
                        "size_bytes": len(wav_bytes),
                    })
                    async with AsyncSessionLocal() as db:
                        existing = await db.scalar(
                            select(VoiceRecordingChunk).where(
                                VoiceRecordingChunk.call_id == self.call_id,
                                VoiceRecordingChunk.chunk_index == chunk_idx,
                            )
                        )
                        if not existing:
                            chunk_record = VoiceRecordingChunk(
                                org_id=self.org_id,
                                call_id=self.call_id,
                                chunk_index=chunk_idx,
                                storage_path=path,
                                duration_seconds=duration_sec,
                                offset_seconds=offset_sec,
                                size_bytes=len(wav_bytes),
                            )
                            db.add(chunk_record)
                        call = await db.get(CallLog, self.call_id)
                        if call and getattr(call, "org_id", None) == self.org_id:
                            call.recording_storage_path = path
                            call.recording_status = "processing"
                        if hasattr(db, "commit"):
                            await db.commit()
            except asyncio.CancelledError:
                break
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
                if not call or getattr(call, "org_id", None) != self.org_id:
                    raise ValueError("Recording call tenant mismatch")
                call.recording_status = "processing"
                if hasattr(db, "commit"):
                    await db.commit()

            remaining = self.buffer.pop_chunk(force=True)
            if remaining:
                wav_bytes, chunk_idx, offset_sec, duration_sec = remaining
                path = await asyncio.wait_for(
                    upload_call_recording_chunk(self.org_id, self.call_id, chunk_idx, wav_bytes),
                    12,
                )
                self.recorded_chunks.append({
                    "chunk_index": chunk_idx,
                    "storage_path": path,
                    "duration_seconds": duration_sec,
                    "offset_seconds": offset_sec,
                    "size_bytes": len(wav_bytes),
                })
                async with AsyncSessionLocal() as db:
                    existing = await db.scalar(
                        select(VoiceRecordingChunk).where(
                            VoiceRecordingChunk.call_id == self.call_id,
                            VoiceRecordingChunk.chunk_index == chunk_idx,
                        )
                    )
                    if not existing:
                        chunk_record = VoiceRecordingChunk(
                            org_id=self.org_id,
                            call_id=self.call_id,
                            chunk_index=chunk_idx,
                            storage_path=path,
                            duration_seconds=duration_sec,
                            offset_seconds=offset_sec,
                            size_bytes=len(wav_bytes),
                        )
                        db.add(chunk_record)
                    call = await db.get(CallLog, self.call_id)
                    if call and getattr(call, "org_id", None) == self.org_id:
                        call.recording_storage_path = path
                    if hasattr(db, "commit"):
                        await db.commit()

            if not self.recorded_chunks:
                async with AsyncSessionLocal() as db:
                    call = await db.get(CallLog, self.call_id)
                    if call and getattr(call, "org_id", None) == self.org_id:
                        call.recording_status = "failed"
                        if hasattr(db, "commit"):
                            await db.commit()
                return None

            final_path = None
            try:
                chunk_wavs = []
                for chunk_meta in self.recorded_chunks:
                    c_bytes = await download_call_recording_chunk(chunk_meta["storage_path"])
                    if c_bytes:
                        chunk_wavs.append(c_bytes)
                if chunk_wavs:
                    stitched_wav = await asyncio.to_thread(stitch_wav_chunks, chunk_wavs)
                    if stitched_wav:
                        final_path = await asyncio.wait_for(
                            upload_call_recording(self.org_id, self.call_id, stitched_wav),
                            12,
                        )
            except Exception:
                logger.warning("Chunk stitching failed for %s, falling back to chunk manifest", self.call_id)

            async with AsyncSessionLocal() as db:
                call = await db.get(CallLog, self.call_id)
                if not call or getattr(call, "org_id", None) != self.org_id:
                    raise ValueError("Recording call tenant mismatch")
                if final_path:
                    call.recording_storage_path = final_path
                    call.recording_status = "ready" if not self.capture_failed else "partial"
                else:
                    last_chunk = self.recorded_chunks[-1]["storage_path"]
                    call.recording_storage_path = last_chunk
                    call.recording_status = "partial"
                call.audio_recording_url = None
                if hasattr(db, "commit"):
                    await db.commit()
            return final_path or self.recorded_chunks[-1]["storage_path"]
        except Exception:
            logger.exception("Call recording finalization failed")
            async with AsyncSessionLocal() as db:
                call = await db.get(CallLog, self.call_id)
                if call and getattr(call, "org_id", None) == self.org_id:
                    call.recording_status = "partial" if call.recording_storage_path else "failed"
                    if hasattr(db, "commit"):
                        await db.commit()
            raise
        finally:
            self.buffer.caller_buffer.clear()
            self.buffer.remote_buffer.clear()
