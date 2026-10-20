import math
import statistics


LATENCY_TARGETS_MS = {"stt_latency_ms": 250, "llm_latency_ms": 400, "tts_latency_ms": 200, "total_latency_ms": 1100}


def milliseconds(value):
    if isinstance(value, (int, float)) and math.isfinite(value) and value >= 0:
        return round(value * 1000)
    return None


def benchmark_summary(turns):
    summary = {}
    for field, target in LATENCY_TARGETS_MS.items():
        values = sorted(turn[field] for turn in turns if isinstance(turn.get(field), (int, float)) and math.isfinite(turn[field]) and turn[field] >= 0)
        summary[field] = {
            "sample_count": len(values),
            "median_ms": round(statistics.median(values)) if values else None,
            "p95_ms": values[max(0, math.ceil(len(values) * 0.95) - 1)] if values else None,
            "target_ms": target,
            "target_met": all(value < target for value in values) if values else None,
        }
    return summary


class VoiceTelemetry:
    def __init__(self):
        self.turns = {}
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.quality_events = []
        self.disconnect_reason = None
        self.requests = set()
        self.stt_audio_seconds = 0.0
        self.tts_audio_seconds = 0.0
        self.tts_characters = 0
        self.cancelled_requests = 0
        self.request_counts = {}

    def record(self, metric):
        kind = getattr(metric, "type", "")
        request_id = getattr(metric, "request_id", None)
        if request_id:
            key = (kind, request_id)
            if key in self.requests:
                return
            self.requests.add(key)
        self.request_counts[kind] = self.request_counts.get(kind, 0) + 1
        if getattr(metric, "cancelled", False):
            self.cancelled_requests += 1
        if kind == "stt_metrics":
            self.stt_audio_seconds += max(0.0, float(getattr(metric, "audio_duration", 0) or 0))
        if kind == "tts_metrics":
            self.tts_audio_seconds += max(0.0, float(getattr(metric, "audio_duration", 0) or 0))
            self.tts_characters += max(0, int(getattr(metric, "characters_count", 0) or 0))
        if kind == "llm_metrics":
            self.prompt_tokens += max(0, int(getattr(metric, "prompt_tokens", 0) or 0))
            self.completion_tokens += max(0, int(getattr(metric, "completion_tokens", 0) or 0))
        speech_id = getattr(metric, "speech_id", None)
        if not speech_id:
            return
        turn = self.turns.setdefault(str(speech_id), {"speech_id": str(speech_id)})
        if kind == "eou_metrics":
            turn["stt_latency_ms"] = milliseconds(getattr(metric, "transcription_delay", None))
            turn["eou_delay_ms"] = milliseconds(getattr(metric, "end_of_utterance_delay", None))
        elif kind == "llm_metrics":
            value = milliseconds(getattr(metric, "ttft", None))
            if "llm_latency_ms" not in turn:
                turn["llm_latency_ms"] = value
            turn["prompt_tokens"] = turn.get("prompt_tokens", 0) + max(0, int(getattr(metric, "prompt_tokens", 0) or 0))
            turn["completion_tokens"] = turn.get("completion_tokens", 0) + max(0, int(getattr(metric, "completion_tokens", 0) or 0))
        elif kind == "tts_metrics" and not getattr(metric, "cancelled", False):
            if "tts_latency_ms" not in turn:
                turn["tts_latency_ms"] = milliseconds(getattr(metric, "ttfb", None))
        parts = [turn.get(key) for key in ("eou_delay_ms", "llm_latency_ms", "tts_latency_ms")]
        turn["total_latency_ms"] = sum(parts) if all(part is not None for part in parts) else None

    def payload(self):
        turns = list(self.turns.values())
        return {"turns": turns, "benchmarks": benchmark_summary(turns),
                "prompt_tokens": self.prompt_tokens, "completion_tokens": self.completion_tokens,
                "quality_events": self.quality_events, "disconnect_reason": self.disconnect_reason,
                "stt_audio_seconds": round(self.stt_audio_seconds, 3),
                "tts_audio_seconds": round(self.tts_audio_seconds, 3),
                "tts_characters": self.tts_characters, "cancelled_requests": self.cancelled_requests,
                "request_counts": self.request_counts,
                "total_latency_method": "EOU delay + first LLM TTFT + first non-cancelled TTS TTFB"}
