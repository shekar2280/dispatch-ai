import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class VoiceRecordingChunk(Base):
    __tablename__ = "voice_recording_chunks"
    __table_args__ = (
        Index("idx_voice_recording_chunks_call_index", "call_id", "chunk_index", unique=True),
        Index("idx_voice_recording_chunks_org_created", "org_id", "created_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    call_id = Column(UUID(as_uuid=True), ForeignKey("call_logs.id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    storage_path = Column(Text, nullable=False)
    duration_seconds = Column(Float, nullable=False, default=0.0)
    offset_seconds = Column(Float, nullable=False, default=0.0)
    size_bytes = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "org_id": str(self.org_id),
            "call_id": str(self.call_id),
            "chunk_index": self.chunk_index,
            "storage_path": self.storage_path,
            "duration_seconds": float(self.duration_seconds),
            "offset_seconds": float(self.offset_seconds),
            "size_bytes": int(self.size_bytes),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
