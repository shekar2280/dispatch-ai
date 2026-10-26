import uuid
from sqlalchemy import Column, String, DateTime, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.core.database import Base

class SystemAuditLog(Base):
    __tablename__ = "system_audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), nullable=True)
    actor_id = Column(UUID(as_uuid=True), nullable=True)
    actor_email = Column(String, nullable=False)
    action_type = Column(String, nullable=False)
    target_id = Column(UUID(as_uuid=True), nullable=True)
    target_name = Column(String, nullable=True)
    old_state = Column(JSONB, nullable=True, default=dict)
    new_state = Column(JSONB, nullable=True, default=dict)
    log_metadata = Column("metadata", JSONB, nullable=True, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
