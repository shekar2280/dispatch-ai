import array
import collections
import io
import logging
import time
import wave
from typing import Optional, List, Dict, Tuple

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
NUM_CHANNELS = 1
BYTES_PER_SAMPLE = 2
BYTES_PER_SEC = SAMPLE_RATE * NUM_CHANNELS * BYTES_PER_SAMPLE
MAX_RECORDING_SEC = 180
MAX_BUFFER_BYTES = BYTES_PER_SEC * MAX_RECORDING_SEC


class ContiguousVADBuffer:
    def __init__(self, session_id: str, preroll_sec: float = 1.0, max_recording_sec: float = MAX_RECORDING_SEC):
        self.session_id = session_id
        self.caller_buffer = bytearray()
        self.remote_buffer = bytearray()
        self.created_at = time.time()
        self.speech_regions: List[Dict[str, float]] = []
        self._current_turn_start_sec: Optional[float] = None
        self.max_buffer_bytes = int(max_recording_sec * BYTES_PER_SEC) // BYTES_PER_SAMPLE * BYTES_PER_SAMPLE
        if self.max_buffer_bytes <= 0:
            raise ValueError("Recording capacity must be positive")
        self.offset_bytes = 0

    def push_frame(self, pcm_chunk: bytes, track_type: str = "caller", offset_sec: Optional[float] = None) -> None:
        if not pcm_chunk:
            return
        if len(pcm_chunk) % BYTES_PER_SAMPLE:
            raise ValueError("PCM frame must contain complete 16-bit samples")
        if track_type not in ("caller", "remote"):
            raise ValueError("Unknown recording track")
        target = self.caller_buffer if track_type == "caller" else self.remote_buffer
        position = len(target) if offset_sec is None else int(max(0, offset_sec) * SAMPLE_RATE) * BYTES_PER_SAMPLE - self.offset_bytes
        if position < 0:
            pcm_chunk = pcm_chunk[-position:]
            position = 0
        finish = position + len(pcm_chunk)
        excess = max(0, finish - self.max_buffer_bytes)
        if excess:
            for buffer in (self.caller_buffer, self.remote_buffer):
                del buffer[:excess]
            self.offset_bytes += excess
            position -= excess
            if position < 0:
                pcm_chunk = pcm_chunk[-position:]
                position = 0
        if len(target) < position + len(pcm_chunk):
            target.extend(b"\x00" * (position + len(pcm_chunk) - len(target)))
        target[position:position + len(pcm_chunk)] = pcm_chunk

    def push_caller_frame(self, pcm_chunk: bytes) -> None:
        self.push_frame(pcm_chunk, track_type="caller")

    def push_agent_staff_frame(self, pcm_chunk: bytes) -> None:
        self.push_frame(pcm_chunk, track_type="remote")

    def on_speech_started(self) -> None:
        current_sec = (self.offset_bytes + len(self.caller_buffer)) / BYTES_PER_SEC
        self._current_turn_start_sec = round(current_sec, 2)

    def on_speech_ended(self) -> None:
        if self._current_turn_start_sec is not None:
            current_sec = (self.offset_bytes + len(self.caller_buffer)) / BYTES_PER_SEC
            start_t = max(0.0, self._current_turn_start_sec)
            end_t = round(current_sec, 2)
            if end_t > start_t:
                self.speech_regions.append({"start": start_t, "end": end_t})
            self._current_turn_start_sec = None

    def get_speech_regions(self) -> List[Dict[str, float]]:
        regions = list(self.speech_regions)
        if self._current_turn_start_sec is not None:
            current_sec = (self.offset_bytes + len(self.caller_buffer)) / BYTES_PER_SEC
            regions.append({
                "start": max(0.0, self._current_turn_start_sec),
                "end": round(current_sec, 2)
            })

        max_len = max(len(self.caller_buffer), len(self.remote_buffer))
        if not regions and max_len > 0:
            total_sec = round(max_len / BYTES_PER_SEC, 2)
            regions = [{"start": 0.0, "end": total_sec}]

        offset_sec = self.offset_bytes / BYTES_PER_SEC
        duration_sec = max_len / BYTES_PER_SEC
        if self.offset_bytes and not self.speech_regions and self._current_turn_start_sec is None:
            return [{"start": 0.0, "end": round(duration_sec, 2)}] if duration_sec else []
        return [{"start": round(max(0, region["start"] - offset_sec), 2),
                 "end": round(min(duration_sec, region["end"] - offset_sec), 2)}
                for region in regions if region["end"] > offset_sec]

    def snapshot_buffers(self) -> Tuple[bytes, bytes]:
        return bytes(self.caller_buffer), bytes(self.remote_buffer)

    def get_mixed_pcm(self) -> bytes:
        return mix_pcm_buffers(*self.snapshot_buffers())

    def generate_wav_bytes(self) -> Optional[bytes]:
        return mix_and_encode_wav(*self.snapshot_buffers())

    def generate_wav_payload(self) -> Tuple[Optional[bytes], List[Dict[str, float]]]:
        wav_bytes = self.generate_wav_bytes()
        regions = self.get_speech_regions()
        return wav_bytes, regions


def mix_pcm_buffers(caller_bytes: bytes, remote_bytes: bytes) -> bytes:
    len_caller = len(caller_bytes)
    len_remote = len(remote_bytes)
    if len_caller == 0 and len_remote == 0:
        return b""
    if len_caller > 0 and len_remote == 0:
        return caller_bytes
    if len_remote > 0 and len_caller == 0:
        return remote_bytes
    max_bytes = max(len_caller, len_remote)
    if max_bytes % BYTES_PER_SAMPLE != 0:
        max_bytes -= (max_bytes % BYTES_PER_SAMPLE)
    buf_a = bytearray(caller_bytes[:max_bytes])
    buf_b = bytearray(remote_bytes[:max_bytes])
    if len(buf_a) < max_bytes:
        buf_a.extend(b"\x00" * (max_bytes - len(buf_a)))
    if len(buf_b) < max_bytes:
        buf_b.extend(b"\x00" * (max_bytes - len(buf_b)))
    arr_a = array.array("h")
    arr_a.frombytes(buf_a)
    arr_b = array.array("h")
    arr_b.frombytes(buf_b)
    arr_mixed = array.array("h")
    for sa, sb in zip(arr_a, arr_b):
        val = sa + sb
        clamped = max(-32768, min(32767, val))
        arr_mixed.append(clamped)
    return arr_mixed.tobytes()


def mix_and_encode_wav(caller_bytes: bytes, remote_bytes: bytes) -> Optional[bytes]:
    pcm_bytes = mix_pcm_buffers(caller_bytes, remote_bytes)
    if not pcm_bytes:
        return None
    try:
        buffer_io = io.BytesIO()
        with wave.open(buffer_io, "wb") as wav_file:
            wav_file.setnchannels(NUM_CHANNELS)
            wav_file.setsampwidth(BYTES_PER_SAMPLE)
            wav_file.setframerate(SAMPLE_RATE)
            wav_file.writeframes(pcm_bytes)
        return buffer_io.getvalue()
    except Exception:
        return None


def stitch_wav_chunks(chunks_wav: List[bytes]) -> bytes:
    valid_chunks = [c for c in chunks_wav if c]
    if not valid_chunks:
        return b""
    if len(valid_chunks) == 1:
        return valid_chunks[0]
    out_io = io.BytesIO()
    with wave.open(out_io, "wb") as out_wav:
        out_wav.setnchannels(NUM_CHANNELS)
        out_wav.setsampwidth(BYTES_PER_SAMPLE)
        out_wav.setframerate(SAMPLE_RATE)
        for chunk_bytes in valid_chunks:
            with wave.open(io.BytesIO(chunk_bytes), "rb") as in_wav:
                frames = in_wav.readframes(in_wav.getnframes())
                out_wav.writeframes(frames)
    return out_io.getvalue()


class ChunkedAudioBuffer:
    def __init__(self, session_id: str, chunk_duration_sec: float = 30.0):
        self.session_id = session_id
        self.chunk_duration_sec = max(1.0, float(chunk_duration_sec))
        self.chunk_bytes_threshold = int(self.chunk_duration_sec * BYTES_PER_SEC)
        self.caller_buffer = bytearray()
        self.remote_buffer = bytearray()
        self.current_chunk_index = 0
        self.current_offset_sec = 0.0

    def push_frame(self, pcm_chunk: bytes, track_type: str = "caller", offset_sec: Optional[float] = None) -> None:
        if not pcm_chunk:
            return
        if len(pcm_chunk) % BYTES_PER_SAMPLE:
            raise ValueError("PCM frame must contain complete 16-bit samples")
        if track_type not in ("caller", "remote"):
            raise ValueError("Unknown recording track")
        target = self.caller_buffer if track_type == "caller" else self.remote_buffer
        if offset_sec is None:
            target.extend(pcm_chunk)
            return
        position = int(max(0.0, offset_sec - self.current_offset_sec) * SAMPLE_RATE) * BYTES_PER_SAMPLE
        if len(target) < position + len(pcm_chunk):
            target.extend(b"\x00" * (position + len(pcm_chunk) - len(target)))
        target[position:position + len(pcm_chunk)] = pcm_chunk

    def push_caller_frame(self, pcm_chunk: bytes) -> None:
        self.push_frame(pcm_chunk, track_type="caller")

    def push_agent_staff_frame(self, pcm_chunk: bytes) -> None:
        self.push_frame(pcm_chunk, track_type="remote")

    def ready_chunk(self) -> bool:
        return max(len(self.caller_buffer), len(self.remote_buffer)) >= self.chunk_bytes_threshold

    def pop_chunk(self, force: bool = False) -> Optional[Tuple[bytes, int, float, float]]:
        max_len = max(len(self.caller_buffer), len(self.remote_buffer))
        if max_len == 0:
            return None
        if not force and max_len < self.chunk_bytes_threshold:
            return None
        chunk_len = min(max_len, self.chunk_bytes_threshold) if not force else max_len
        if chunk_len % BYTES_PER_SAMPLE != 0:
            chunk_len -= (chunk_len % BYTES_PER_SAMPLE)
        if chunk_len == 0:
            return None
        caller_slice = bytes(self.caller_buffer[:chunk_len])
        remote_slice = bytes(self.remote_buffer[:chunk_len])
        del self.caller_buffer[:chunk_len]
        del self.remote_buffer[:chunk_len]
        wav = mix_and_encode_wav(caller_slice, remote_slice)
        if not wav:
            return None
        duration_sec = round(chunk_len / BYTES_PER_SEC, 2)
        chunk_idx = self.current_chunk_index
        offset_sec = self.current_offset_sec
        self.current_chunk_index += 1
        self.current_offset_sec = round(self.current_offset_sec + duration_sec, 2)
        return wav, chunk_idx, offset_sec, duration_sec


_active_session_buffers: Dict[str, ContiguousVADBuffer] = {}
_finalized_wav_cache: collections.OrderedDict[str, bytes] = collections.OrderedDict()
MAX_FINAL_CACHE_ITEMS = 50


def cache_final_wav(session_id: str, wav_bytes: bytes) -> None:
    if not wav_bytes:
        return
    _finalized_wav_cache[session_id] = wav_bytes
    if len(_finalized_wav_cache) > MAX_FINAL_CACHE_ITEMS:
        _finalized_wav_cache.popitem(last=False)


def get_cached_wav(session_id: str) -> Optional[bytes]:
    return _finalized_wav_cache.get(session_id)


def get_or_create_buffer(session_id: str) -> ContiguousVADBuffer:
    if session_id not in _active_session_buffers:
        _active_session_buffers[session_id] = ContiguousVADBuffer(session_id)
    return _active_session_buffers[session_id]


def remove_session_buffer(session_id: str) -> None:
    if session_id in _active_session_buffers:
        buf = _active_session_buffers[session_id]
        wav = buf.generate_wav_bytes()
        if wav:
            cache_final_wav(session_id, wav)
        del _active_session_buffers[session_id]
