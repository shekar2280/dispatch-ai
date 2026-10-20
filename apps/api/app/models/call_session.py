import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Boolean, Text, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.core.database import Base


class CallLog(Base):
    __tablename__ = "call_logs"
    __table_args__ = (
        Index("idx_call_logs_org_start_time", "org_id", "start_time"),
        Index("idx_call_logs_org_call_status", "org_id", "call_status"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    caller_phone = Column(String, nullable=False)
    caller_name = Column(String, nullable=True)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id", ondelete="SET NULL"), nullable=True)
    session_type = Column(String, default="voice_simulator")
    triage_status = Column(String, default="admin")
    intent_classification = Column(String, default="UNCLASSIFIED")
    triage_latency_ms = Column(Integer, default=0)
    call_outcome = Column(String, default="inquiry")
    attended_by = Column(String, default="AI Receptionist")
    chief_complaint = Column(Text, nullable=True)
    total_turns = Column(Integer, default=0)
    duration_seconds = Column(Integer, default=0)
    ai_speaking_seconds = Column(Integer, default=0)
    user_speaking_seconds = Column(Integer, default=0)
    stt_total_ms = Column(Integer, default=0)
    tts_total_ms = Column(Integer, default=0)
    turns = Column(JSONB, default=list)
    full_transcript = Column(Text, nullable=True)
    sentiment_score = Column(String, default="satisfied")
    security_flagged = Column(Boolean, default=False)
    recording_status = Column(String(20), default="disabled", nullable=False)
    recording_storage_path = Column(Text, nullable=True)
    audio_recording_url = Column(Text, nullable=True)
    telemetry_summary = Column(JSONB, nullable=False, default=dict)
    call_budget_seconds = Column(Integer, nullable=False, default=120)
    caller_identity = Column(String, nullable=True)
    provider_call_sid = Column(String, nullable=True)
    admission_expires_at = Column(DateTime(timezone=True), nullable=True)
    provider_started_at = Column(DateTime(timezone=True), nullable=True)
    deadline_at = Column(DateTime(timezone=True), nullable=True)
    quota_charged_at = Column(DateTime(timezone=True), nullable=True)
    charged_seconds = Column(Integer, nullable=False, default=0)
    end_reason = Column(String, nullable=True)
    media_terminated_at = Column(DateTime(timezone=True), nullable=True)
    booking_proposal = Column(JSONB, nullable=True)
    booking_result = Column(JSONB, nullable=True)
    room_name = Column(String, nullable=True)
    call_status = Column(String(20), default="ringing", nullable=False)
    start_time = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    connected_at = Column(DateTime(timezone=True), nullable=True)
    agent_joined_at = Column(DateTime(timezone=True), nullable=True)
    end_time = Column(DateTime(timezone=True), nullable=True)


VoiceCallSession = CallLog
