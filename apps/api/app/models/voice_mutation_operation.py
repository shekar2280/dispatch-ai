import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class VoiceMutationOperation(Base):
    __tablename__ = "voice_mutation_operations"
    __table_args__ = (
        Index("idx_voice_mutations_org_key", "org_id", "operation_key"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    call_id = Column(UUID(as_uuid=True), ForeignKey("call_logs.id", ondelete="SET NULL"), nullable=True)
    operation_key = Column(String(255), nullable=False, unique=True)
    operation_type = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default="completed")
    response_payload = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
