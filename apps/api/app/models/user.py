import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Boolean, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from app.core.database import Base

user_role_enum = SQLEnum(
    "admin", "doctor", "receptionist", "staff",
    name="user_role",
    create_type=False
)

presence_status_enum = SQLEnum(
    "available", "busy", "offline", "on_leave", "running_late", "unavailable",
    name="presence_status",
    create_type=False
)

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
    email = Column(String, nullable=False, unique=True)
    full_name = Column(String, nullable=False)
    role = Column(user_role_enum, nullable=False, default="receptionist")
    specialization = Column(String, nullable=True, default="General Medicine")
    phone_number = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    @property
    def presence_status(self) -> str:
        return "available"

