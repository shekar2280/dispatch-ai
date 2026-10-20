import uuid
from sqlalchemy import Column, String, DateTime, Date, Integer, func, cast, Enum as SQLEnum
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.core.database import Base

appointment_status_enum = SQLEnum(
    "scheduled", "in_progress", "completed", "cancelled", "no_show", "arrived", "skipped",
    name="appointment_status",
    create_type=False,
    values_callable=lambda x: [e.value if hasattr(e, "value") else str(e) for e in x]
)

appointment_source_enum = SQLEnum(
    "ai_voice", "walk_in", "manual",
    name="appointment_source",
    create_type=False,
    values_callable=lambda x: [e.value if hasattr(e, "value") else str(e) for e in x]
)


class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), nullable=False)
    patient_id = Column(UUID(as_uuid=True), nullable=False)
    doctor_id = Column(UUID(as_uuid=True), nullable=True)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    appointment_timezone = Column(String, nullable=True)
    status = Column(appointment_status_enum, nullable=False, default="scheduled")
    queue_state = Column(String(20), nullable=False, default="not_checked_in")
    encounter_state = Column(String(20), nullable=False, default="not_started")
    called_at = Column(DateTime(timezone=True), nullable=True)
    call_count = Column(Integer, nullable=False, default=0)
    chief_complaint = Column(String, nullable=True)
    doctor_notes = Column(String, nullable=True)
    source = Column(appointment_source_enum, default="ai_voice")
    call_session_id = Column(UUID(as_uuid=True), nullable=True)
    cancellation_reason = Column(String, nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    token_number = Column(Integer, nullable=True)
    display_token = Column(String(10), nullable=True)
    shift_type = Column(String(10), nullable=True)

    @hybrid_property
    def appointment_date(self):
        if not self.start_time:
            return None
        st = self.start_time
        from zoneinfo import ZoneInfo
        timezone = self.appointment_timezone or getattr(st.tzinfo, "key", None)
        if not timezone:
            raise ValueError("Appointment timezone is missing")
        st = st.astimezone(ZoneInfo(timezone))
        return st.date()

    @appointment_date.setter
    def appointment_date(self, value):
        pass

    @appointment_date.expression
    def appointment_date(cls):
        return cast(func.timezone(cls.appointment_timezone, cls.start_time), Date)

    @hybrid_property
    def appointment_time(self):
        if not self.start_time:
            return None
        st = self.start_time
        from zoneinfo import ZoneInfo
        timezone = self.appointment_timezone or getattr(st.tzinfo, "key", None)
        if not timezone:
            raise ValueError("Appointment timezone is missing")
        st = st.astimezone(ZoneInfo(timezone))
        h = st.hour
        m = st.minute
        h12 = h % 12 or 12
        ampm = "AM" if h < 12 else "PM"
        return f"{h12:02d}:{m:02d} {ampm}"

    @appointment_time.setter
    def appointment_time(self, value):
        pass

    @property
    def verification_status(self):
        return getattr(self, "_verification_status", "verified")

    @verification_status.setter
    def verification_status(self, value):
        self._verification_status = value

    @property
    def auto_confirm_deadline(self):
        return getattr(self, "_auto_confirm_deadline", None)

    @auto_confirm_deadline.setter
    def auto_confirm_deadline(self, value):
        self._auto_confirm_deadline = value

    @property
    def token_prefix(self):
        return getattr(self, "_token_prefix", None) or (self.display_token[0] if self.display_token and self.display_token[0].isalpha() else None)

    @token_prefix.setter
    def token_prefix(self, value):
        self._token_prefix = value

    @property
    def payment_status(self):
        if self.booking_metadata and "payment_status" in self.booking_metadata:
            return self.booking_metadata["payment_status"]
        return getattr(self, "_payment_status", "pending")

    @payment_status.setter
    def payment_status(self, value):
        self._payment_status = value
        if self.booking_metadata is None:
            self.booking_metadata = {}
        meta = dict(self.booking_metadata)
        meta["payment_status"] = value
        self.booking_metadata = meta
        try:
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(self, "booking_metadata")
        except Exception:
            pass

    @property
    def payment_method(self):
        if self.booking_metadata and "payment_method" in self.booking_metadata:
            return self.booking_metadata["payment_method"]
        return getattr(self, "_payment_method", None)

    @payment_method.setter
    def payment_method(self, value):
        self._payment_method = value
        if self.booking_metadata is None:
            self.booking_metadata = {}
        meta = dict(self.booking_metadata)
        meta["payment_method"] = value
        self.booking_metadata = meta
        try:
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(self, "booking_metadata")
        except Exception:
            pass

    @property
    def fee(self):
        if self.booking_metadata and "fee" in self.booking_metadata:
            return self.booking_metadata["fee"]
        return getattr(self, "_fee", 0)

    @fee.setter
    def fee(self, value):
        self._fee = value
        if self.booking_metadata is None:
            self.booking_metadata = {}
        meta = dict(self.booking_metadata)
        meta["fee"] = value
        self.booking_metadata = meta
        try:
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(self, "booking_metadata")
        except Exception:
            pass

    booking_metadata = Column(JSONB, nullable=True, default=dict)


    checked_in_at = Column(DateTime(timezone=True), nullable=True)
    checked_in_by = Column(UUID(as_uuid=True), nullable=True)
    consultation_started_at = Column(DateTime(timezone=True), nullable=True)
    consultation_ended_at = Column(DateTime(timezone=True), nullable=True)
    actual_duration_seconds = Column(Integer, nullable=True)
