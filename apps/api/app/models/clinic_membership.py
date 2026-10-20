import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Numeric, func, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base
from app.models.user import user_role_enum


class ClinicMembership(Base):
    __tablename__ = "clinic_memberships"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    invited_email = Column(String, nullable=True, index=True)
    role = Column(user_role_enum, nullable=False, default="receptionist")
    display_name = Column(String, nullable=True)
    status = Column(String, nullable=False, default="active")
    total_consultations = Column(Integer, nullable=False, default=0)
    total_minutes_worked = Column(Integer, nullable=False, default=0)
    total_walkins_triaged = Column(Integer, nullable=False, default=0)
    total_revenue_collected = Column(Numeric(12, 2), nullable=False, default=0.00)
    joined_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
