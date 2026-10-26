import uuid
from datetime import time
from sqlalchemy import Column, Time, Integer, Boolean
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from app.core.database import Base

class DoctorSchedule(Base):
    __tablename__ = "doctor_schedules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), nullable=False)
    doctor_id = Column(UUID(as_uuid=True), nullable=False)
    shift_start = Column(Time, nullable=False, default=time(9, 0))
    shift_end = Column(Time, nullable=False, default=time(17, 0))
    lunch_start = Column(Time, nullable=False, default=time(12, 0))
    lunch_end = Column(Time, nullable=False, default=time(13, 0))
    surgery_start = Column(Time, nullable=True)
    surgery_end = Column(Time, nullable=True)
    working_days = Column(ARRAY(Integer), default=[1, 2, 3, 4, 5, 6])
    slot_duration_minutes = Column(Integer, nullable=False, default=30)
    is_active = Column(Boolean, default=True)

