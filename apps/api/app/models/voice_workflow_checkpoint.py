import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class VoiceWorkflowCheckpoint(Base):
    __tablename__ = "voice_workflow_checkpoints"
    __table_args__ = (
        Index("idx_workflow_checkpoints_org_call", "org_id", "call_id", unique=True),
        Index("idx_workflow_checkpoints_expiry_status", "expires_at", "status"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    call_id = Column(UUID(as_uuid=True), nullable=False)
    resumed_from_call_id = Column(UUID(as_uuid=True), nullable=True)
    workflow_version = Column(Integer, nullable=False, default=1)
    state_version = Column(Integer, nullable=False, default=1)
    status = Column(String, nullable=False, default="active")
    stage = Column(String, nullable=False, default="intake")
    safe_state = Column(JSONB, nullable=False, default=dict)
    last_completed_event_id = Column(String, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    resumed_at = Column(DateTime(timezone=True), nullable=True)
