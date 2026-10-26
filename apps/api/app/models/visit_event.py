import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class VisitEvent(Base):
    __tablename__ = "visit_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Visit events are append-only history for an appointment. If a test or a
    # tenant purge hard-deletes the appointment, remove its dependent events
    # with it rather than leaving an orphaned audit trail.
    visit_id = Column(
        UUID(as_uuid=True),
        ForeignKey("appointments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    org_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    event_type = Column(String, nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    actor_id = Column(UUID(as_uuid=True), nullable=True)
    actor_type = Column(String, nullable=False, default="staff")
    notes = Column(String, nullable=True)
    event_metadata = Column(JSONB, nullable=False, default=dict)
