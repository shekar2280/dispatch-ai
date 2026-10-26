import time
from typing import Dict, Any, Tuple
from dataclasses import dataclass, field


@dataclass
class ProviderCapacityTracker:
    window_seconds: int = 60
    max_tokens_per_minute: int = 2000000
    max_requests_per_minute: int = 600
    warning_threshold_ratio: float = 0.80
    request_timestamps: list = field(default_factory=list)
    token_records: list = field(default_factory=list)

    def record_usage(self, estimated_tokens: int = 150):
        now = time.time()
        self.request_timestamps.append(now)
        self.token_records.append((now, estimated_tokens))
        self._prune(now)

    def _prune(self, now: float):
        cutoff = now - self.window_seconds
        self.request_timestamps = [t for t in self.request_timestamps if t > cutoff]
        self.token_records = [rec for rec in self.token_records if rec[0] > cutoff]

    def is_tier1_congested(self) -> bool:
        now = time.time()
        self._prune(now)
        current_rpm = len(self.request_timestamps)
        current_tpm = sum(tokens for _, tokens in self.token_records)

        rpm_ratio = current_rpm / max(1, self.max_requests_per_minute)
        tpm_ratio = current_tpm / max(1, self.max_tokens_per_minute)

        return rpm_ratio >= self.warning_threshold_ratio or tpm_ratio >= self.warning_threshold_ratio

    def get_load_metrics(self) -> Dict[str, Any]:
        now = time.time()
        self._prune(now)
        current_rpm = len(self.request_timestamps)
        current_tpm = sum(tokens for _, tokens in self.token_records)
        return {
            "current_rpm": current_rpm,
            "current_tpm": current_tpm,
            "rpm_ratio": round(current_rpm / max(1, self.max_requests_per_minute), 3),
            "tpm_ratio": round(current_tpm / max(1, self.max_tokens_per_minute), 3),
            "congested": self.is_tier1_congested(),
        }


gemini_capacity_tracker = ProviderCapacityTracker()


class ClinicVoiceRouter:
    VALID_INTENTS = {
        "SCHEDULE_APPOINTMENT",
        "RESCHEDULE_APPOINTMENT",
        "CANCEL_APPOINTMENT",
        "CLINIC_TIMINGS_INQUIRY",
        "DOCTOR_AVAILABILITY_INQUIRY",
        "UNKNOWN",
    }

    @staticmethod
    def select_voice_engines(requested_persona: str = "gemini-aoede") -> Tuple[str, str, str]:
        is_congested = gemini_capacity_tracker.is_tier1_congested()

        if not is_congested:
            stt_engine = "deepgram_nova2"
            tts_engine = requested_persona if requested_persona.startswith("gemini-") else "gemini-aoede"
            tier = "TIER_1_PRIMARY"
        else:
            stt_engine = "groq_whisper_v3"
            tts_engine = "flux-priya-en"
            tier = "TIER_2_OVERFLOW"

        return stt_engine, tts_engine, tier

    @staticmethod
    def classify_clinic_intent(user_transcript: str) -> Dict[str, Any]:
        text = user_transcript.lower()

        if any(w in text for w in ["reschedule", "change time", "move appointment", "postpone", "prepone"]):
            intent = "RESCHEDULE_APPOINTMENT"
        elif any(w in text for w in ["cancel", "delete appointment", "don't want to come", "wont come"]):
            intent = "CANCEL_APPOINTMENT"
        elif any(w in text for w in ["open", "timings", "hours", "close", "timing", "working days"]):
            intent = "CLINIC_TIMINGS_INQUIRY"
        elif any(w in text for w in ["doctor available", "dr available", "is doctor in", "consultation slots", "doctor free"]):
            intent = "DOCTOR_AVAILABILITY_INQUIRY"
        elif any(w in text for w in ["appointment", "book", "consult", "doctor", "visit", "checkup"]):
            intent = "SCHEDULE_APPOINTMENT"
        else:
            intent = "UNKNOWN"

        return {
            "intent": intent,
            "raw_text": user_transcript,
        }
