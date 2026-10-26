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
    def __init__(self, call_session_id=None, provider="unknown", model="unknown", workflow_stage="intake"):
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
        self.call_session_id = str(call_session_id) if call_session_id else None
        self.provider = provider
        self.model = model
        self.workflow_stage = workflow_stage
        self.llm_requests = []
        self.llm_request_ids = set()
        self.pending_shapes = []
        self.provider_errors = []

    def set_context(self, call_session_id=None, provider=None, model=None, workflow_stage=None):
        if call_session_id is not None:
            self.call_session_id = str(call_session_id)
        if provider is not None:
            self.provider = provider
        if model is not None:
            self.model = model
        if workflow_stage is not None:
            self.workflow_stage = workflow_stage

    def stage_request_shape(self, **kwargs):
        self.pending_shapes.append(kwargs)

    def record_error(self, error):
        entry = {
            "category": getattr(error.category, "value", str(error.category)) if hasattr(error, "category") else "unknown",
            "recoverable": bool(getattr(error, "recoverable", False)),
            "status_code": getattr(error, "status_code", None),
            "request_id": getattr(error, "request_id", None),
            "retry_after": getattr(error, "retry_after", None),
            "sanitized_message": getattr(error, "sanitized_message", str(error)),
        }
        self.provider_errors.append(entry)

    def record_llm_request(self, request_entry):
        req_id = request_entry.get("request_id")
        if req_id:
            if req_id in self.llm_request_ids:
                return
            self.llm_request_ids.add(req_id)
        prompt_tokens = max(0, int(request_entry.get("prompt_tokens", 0) or 0))
        completion_tokens = max(0, int(request_entry.get("completion_tokens", 0) or 0))
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.llm_requests.append(request_entry)

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
            prompt = max(0, int(getattr(metric, "prompt_tokens", 0) or 0))
            completion = max(0, int(getattr(metric, "completion_tokens", 0) or 0))
            self.prompt_tokens += prompt
            self.completion_tokens += completion
            raw_reasoning = getattr(metric, "reasoning_tokens", None)
            if raw_reasoning is None and hasattr(metric, "metadata") and isinstance(metric.metadata, dict):
                raw_reasoning = metric.metadata.get("reasoning_tokens")
            reasoning = int(raw_reasoning) if isinstance(raw_reasoning, (int, float)) and math.isfinite(raw_reasoning) and raw_reasoning >= 0 else "unknown"
            raw_total = getattr(metric, "total_tokens", None)
            total = int(raw_total) if isinstance(raw_total, (int, float)) and math.isfinite(raw_total) and raw_total > 0 else (prompt + completion + (reasoning if isinstance(reasoning, int) else 0))
            speech = getattr(metric, "speech_id", None)
            req_key = request_id or f"llm-req-{len(self.llm_requests) + 1}"
            if req_key not in self.llm_request_ids:
                self.llm_request_ids.add(req_key)
                duration_val = getattr(metric, "duration", None)
                ttft_val = getattr(metric, "ttft", None)
                lat = milliseconds(duration_val) or milliseconds(ttft_val)
                is_cancelled = bool(getattr(metric, "cancelled", False))
                shape = self.pending_shapes.pop(0) if self.pending_shapes else {}
                entry = {
                    "request_id": req_key,
                    "call_id": self.call_session_id,
                    "speech_id": str(speech) if speech else None,
                    "workflow_stage": shape.get("workflow_stage", self.workflow_stage),
                    "provider": shape.get("provider", self.provider),
                    "model": shape.get("model", self.model),
                    "tool_names": shape.get("tool_names", []),
                    "tool_count": shape.get("tool_count", len(shape.get("tool_names", []))),
                    "history_item_count": shape.get("history_item_count", 0),
                    "instruction_characters": shape.get("instruction_characters", 0),
                    "serialized_history_characters": shape.get("serialized_history_characters", 0),
                    "serialized_tool_schema_characters": shape.get("serialized_tool_schema_characters", 0),
                    "tool_result_characters": shape.get("tool_result_characters", 0),
                    "prompt_tokens": prompt,
                    "completion_tokens": completion,
                    "reasoning_tokens": reasoning,
                    "total_tokens": total,
                    "is_retry": bool(getattr(metric, "is_retry", False) or shape.get("is_retry", False)),
                    "status": "cancelled" if is_cancelled else "success",
                    "latency_ms": lat,
                }
                self.llm_requests.append(entry)
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
        return {
            "turns": turns,
            "benchmarks": benchmark_summary(turns),
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.prompt_tokens + self.completion_tokens,
            "llm_requests": self.llm_requests,
            "quality_events": self.quality_events,
            "disconnect_reason": self.disconnect_reason,
            "stt_audio_seconds": round(self.stt_audio_seconds, 3),
            "tts_audio_seconds": round(self.tts_audio_seconds, 3),
            "tts_characters": self.tts_characters,
            "cancelled_requests": self.cancelled_requests,
            "request_counts": self.request_counts,
            "provider_errors": self.provider_errors,
            "total_latency_method": "EOU delay + first LLM TTFT + first non-cancelled TTS TTFB",
        }
