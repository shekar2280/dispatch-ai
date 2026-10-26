import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base

class VoiceCallTurn(Base):
    __tablename__ = "voice_call_turns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("call_logs.id", ondelete="CASCADE"), nullable=False)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    turn_number = Column(Integer, nullable=False)
    user_transcript = Column(Text, nullable=True)
    user_audio_url = Column(Text, nullable=True)
    ai_filler_text = Column(Text, nullable=True)
    ai_filler_audio_url = Column(Text, nullable=True)
    ai_response_text = Column(Text, nullable=True)
    ai_response_audio_url = Column(Text, nullable=True)
    stt_latency_ms = Column(Integer, nullable=True)
    llm_latency_ms = Column(Integer, nullable=True)
    tts_latency_ms = Column(Integer, nullable=True)
    total_latency_ms = Column(Integer, nullable=True)
    speech_id = Column(String, nullable=True)
    event_id = Column(String, nullable=True)
    interrupted = Column(Boolean, nullable=False, default=False)
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

CallTurn = VoiceCallTurn
