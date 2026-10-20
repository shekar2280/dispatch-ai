import uuid
from sqlalchemy import Column, String, Date, DateTime, Boolean, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.core.database import Base


class Patient(Base):
    __tablename__ = "patients"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), nullable=False)
    phone_number = Column(String, index=True, nullable=False)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    dob = Column(Date, nullable=True)
    gender = Column(String, nullable=True)
    blood_group = Column(String, nullable=True, index=True)
    email = Column(String, nullable=True)
    address = Column(String, nullable=True)
    medical_history = Column(JSONB, nullable=True, default=dict)
    recent_diagnosis = Column(String, nullable=True)
    created_by_type = Column(String, nullable=True, default="VOICE_AI")
    created_by = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    @property
    def emergency_contact_name(self):
        return None

    @property
    def emergency_contact_phone(self):
        return None

    @property
    def hipaa_consent_given(self):
        return None

