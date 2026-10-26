import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Numeric, func, Enum as SQLEnum
from sqlalchemy.orm import synonym
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base

payment_status_enum = SQLEnum(
    "paid", "pending", "refunded",
    name="payment_status",
    create_type=False,
    values_callable=lambda x: [e.value if hasattr(e, "value") else str(e) for e in x]
)


class PaymentReceipt(Base):
    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    visit_id = Column("appointment_id", UUID(as_uuid=True), ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False, index=True)
    appointment_id = synonym("visit_id")
    amount = Column(Numeric(12, 2), nullable=False)
    status = Column(payment_status_enum, nullable=False)
    method = Column(String(20), nullable=False)
    reference = Column(String(120), nullable=True)
    received_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    received_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


Payment = PaymentReceipt
