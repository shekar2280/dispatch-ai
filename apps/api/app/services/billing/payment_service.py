from app.core.clinic_config import require_clinic_timezone
from datetime import datetime, date, timedelta
import zoneinfo
from decimal import Decimal
from typing import Optional, Dict, Any, List
from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, or_, and_, exists, cast, Integer, update
from sqlalchemy.orm.attributes import flag_modified

from app.models.organization import Organization
from app.models.appointment import Appointment
from app.models.patient import Patient
from app.models.payment_receipt import PaymentReceipt
from app.models.clinic_membership import ClinicMembership
from app.models.user import User
from app.schemas.appointment import ClinicPaymentUpdate


def money(value):
    amount = Decimal(str(value or 0))
    if not amount.is_finite() or amount < 0 or amount != amount.quantize(Decimal("0.01")):
        raise HTTPException(422, "Amounts must be non-negative and have at most two decimal places")
    return amount


def calculate_bill(items):
    total = Decimal("0.00")
    normalized = []
    for item in items:
        amount = money(item.amount)
        if item.unit_price is not None:
            computed = (money(item.unit_price) * Decimal(str(item.quantity or 1))).quantize(Decimal("0.01"))
            if amount != computed:
                raise HTTPException(422, "Item amount must equal quantity times unit price")
        total += amount
        normalized.append(item.model_dump(mode="json"))
    return total, normalized


async def collect_appointment_fee(
    db: AsyncSession, appointment_id: UUID, req: ClinicPaymentUpdate,
    org_id: UUID, received_by_id: Optional[UUID] = None,
) -> Dict[str, Any]:
    import hashlib
    import json
    clinic_appt = await db.scalar(select(Appointment).where(
        Appointment.id == appointment_id, Appointment.org_id == org_id,
    ).with_for_update())
    if not clinic_appt:
        raise HTTPException(404, "Clinic appointment not found")
    meta = dict(clinic_appt.booking_metadata or {})
    requests = dict(meta.get("settlement_requests") or {})
    fingerprint = hashlib.sha256(json.dumps(req.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()
    previous = requests.get(req.idempotency_key)
    if previous:
        if previous["fingerprint"] != fingerprint:
            raise HTTPException(409, "This payment reference was already used for another request")
        return previous["response"]
    if clinic_appt.status != "completed":
        raise HTTPException(409, "Complete consultation before finalizing the bill")
    total, items = calculate_bill(req.bill_items) if req.bill_items is not None else (money(clinic_appt.fee), meta.get("bill_items", []))
    if req.fee is not None and money(req.fee) != total:
        raise HTTPException(422, "Bill total does not match its items")
    paid = money(await db.scalar(select(func.coalesce(func.sum(PaymentReceipt.amount), 0)).where(
        PaymentReceipt.visit_id == clinic_appt.id, PaymentReceipt.org_id == org_id,
        PaymentReceipt.status == "paid",
    )) or 0)
    if clinic_appt.payment_status == "paid" and not paid and money(clinic_appt.fee) > 0:
        raise HTTPException(409, "Legacy payment needs receipt reconciliation before further collection")
    changed = meta.get("bill_finalized_at") and (items != meta.get("bill_items", []) or total != money(clinic_appt.fee))
    if changed and not (req.adjustment_reason or "").strip():
        raise HTTPException(409, "A finalized bill adjustment requires a reason")
    if total < paid:
        raise HTTPException(409, "Bill cannot be reduced below received payments; resolve the credit first")
    now = datetime.now(zoneinfo.ZoneInfo("UTC")).isoformat()
    if changed:
        adjustments = list(meta.get("bill_adjustments") or [])
        adjustments.append({"previous_items": meta.get("bill_items", []), "previous_total": float(money(clinic_appt.fee)), "reason": req.adjustment_reason, "actor_id": str(received_by_id) if received_by_id else None, "at": now})
        meta["bill_adjustments"] = adjustments
    receipt_id = None
    amount = Decimal("0.00")
    if req.payment_status == "paid" and total > paid:
        if req.payment_method not in {"Cash", "UPI"}:
            raise HTTPException(422, "Choose Cash or UPI")
        if req.amount_received is None:
            raise HTTPException(422, "Enter the amount actually received")
        amount = money(req.amount_received)
        if amount <= 0:
            raise HTTPException(422, "Payment amount must be greater than zero")
        if amount > total - paid:
            raise HTTPException(422, "Payment amount received can be no more than the outstanding balance")
        receipt = PaymentReceipt(org_id=org_id, visit_id=clinic_appt.id, amount=amount, status="paid",
                                 method=req.payment_method, reference=req.reference, received_by=received_by_id)
        db.add(receipt)
        await db.flush()
        receipt_id = str(receipt.id)
        paid += amount
        if received_by_id:
            await db.execute(update(ClinicMembership).where(ClinicMembership.org_id == org_id, ClinicMembership.user_id == received_by_id).values(total_revenue_collected=func.coalesce(ClinicMembership.total_revenue_collected, 0) + amount))
    elif req.amount_received is not None:
        raise HTTPException(409, "There is no balance to collect")
    meta.update({"fee": float(total), "bill_items": items, "bill_finalized_at": meta.get("bill_finalized_at") or now,
                 "payment_status": "paid" if paid == total else "pending"})
    if amount:
        meta.update({"payment_method": req.payment_method, "collected_at": now})
    result = {"appointment_id": str(clinic_appt.id), "fee": float(total), "bill_items": items,
              "payment_status": meta["payment_status"], "payment_method": meta.get("payment_method"),
              "amount_paid": float(paid), "balance_due": float(total - paid),
              "bill_finalized_at": meta["bill_finalized_at"], "receipt_id": receipt_id}
    requests[req.idempotency_key] = {"fingerprint": fingerprint, "response": result}
    meta["settlement_requests"] = requests
    clinic_appt.booking_metadata = meta
    clinic_appt.fee = float(total)
    clinic_appt.payment_status = meta["payment_status"]
    if paid > 0 and paid < total:
        clinic_appt.payment_method = "partial"
    elif amount:
        clinic_appt.payment_method = req.payment_method
    await db.commit()
    return result


async def get_clinic_revenue_data(
    db: AsyncSession, org_id: UUID, period: str = "today"
) -> Dict[str, Any]:
    clinic_org = await db.get(Organization, org_id)
    if not clinic_org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinic organization not found",
        )

    tz_str = require_clinic_timezone(clinic_org)
    tz = zoneinfo.ZoneInfo(tz_str)
    today_local = datetime.now(tz).date()

    query = (
        select(Appointment, Patient)
        .outerjoin(Patient, Appointment.patient_id == Patient.id)
        .where(
            Appointment.org_id == org_id,
            Appointment.status != "cancelled",
        )
    )

    today_iso = today_local.isoformat()
    period_start = today_local
    if period == "today":
        receipt_since = datetime.combine(today_local, datetime.min.time(), tzinfo=tz)
        query = query.where(
            or_(
                Appointment.appointment_date == today_local,
                exists(
                    select(PaymentReceipt.id).where(
                        PaymentReceipt.visit_id == Appointment.id,
                        PaymentReceipt.org_id == org_id,
                        PaymentReceipt.received_at >= receipt_since,
                    )
                ),
                and_(
                    Appointment.payment_status == "paid",
                    Appointment.booking_metadata["collected_at"].astext.startswith(
                        today_iso
                    ),
                ),
            )
        )
    elif period == "week":
        week_ago = today_local - timedelta(days=7)
        period_start = week_ago
        receipt_since = datetime.combine(week_ago, datetime.min.time(), tzinfo=tz)
        week_iso = week_ago.isoformat()
        query = query.where(
            or_(
                Appointment.appointment_date >= week_ago,
                exists(
                    select(PaymentReceipt.id).where(
                        PaymentReceipt.visit_id == Appointment.id,
                        PaymentReceipt.org_id == org_id,
                        PaymentReceipt.received_at >= receipt_since,
                    )
                ),
                and_(
                    Appointment.payment_status == "paid",
                    Appointment.booking_metadata["collected_at"].astext >= week_iso,
                ),
            )
        )
    elif period == "month":
        month_ago = today_local - timedelta(days=30)
        period_start = month_ago
        receipt_since = datetime.combine(month_ago, datetime.min.time(), tzinfo=tz)
        month_iso = month_ago.isoformat()
        query = query.where(
            or_(
                Appointment.appointment_date >= month_ago,
                exists(
                    select(PaymentReceipt.id).where(
                        PaymentReceipt.visit_id == Appointment.id,
                        PaymentReceipt.org_id == org_id,
                        PaymentReceipt.received_at >= receipt_since,
                    )
                ),
                and_(
                    Appointment.payment_status == "paid",
                    Appointment.booking_metadata["collected_at"].astext >= month_iso,
                ),
            )
        )
    elif period == "year":
        year_ago = today_local - timedelta(days=365)
        period_start = year_ago
        receipt_since = datetime.combine(year_ago, datetime.min.time(), tzinfo=tz)
        year_iso = year_ago.isoformat()
        query = query.where(
            or_(
                Appointment.appointment_date >= year_ago,
                exists(
                    select(PaymentReceipt.id).where(
                        PaymentReceipt.visit_id == Appointment.id,
                        PaymentReceipt.org_id == org_id,
                        PaymentReceipt.received_at >= receipt_since,
                    )
                ),
                and_(
                    Appointment.payment_status == "paid",
                    Appointment.booking_metadata["collected_at"].astext >= year_iso,
                ),
            )
        )

    res = await db.execute(query)
    rows = res.all()

    receipt_rows = (
        (
            await db.execute(
                select(PaymentReceipt).where(PaymentReceipt.org_id == org_id)
            )
        )
        .scalars()
        .all()
    )
    receipts_by_visit = {}
    for receipt in receipt_rows:
        receipts_by_visit.setdefault(receipt.visit_id, []).append(receipt)

    total_settled = 0
    total_pending = 0
    upi_total = 0
    cash_total = 0
    transactions = []

    for appt, patient in rows:
        fee_amount = appt.fee if appt.fee is not None else 0
        p_name = f"{patient.first_name} {patient.last_name}".strip() if patient else ""
        p_phone = patient.phone_number if patient else ""

        receipts = receipts_by_visit.get(appt.id, [])
        amount_paid = sum(float(receipt.amount) for receipt in receipts)
        period_receipts = [
            r for r in receipts if r.received_at.astimezone(tz).date() >= period_start
        ]
        amount_collected_period = sum(float(r.amount) for r in period_receipts)
        balance_due = max(float(fee_amount) - amount_paid, 0)
        is_settled = balance_due == 0
        methods = list(dict.fromkeys(receipt.method for receipt in receipts))
        pay_method = (
            " + ".join(methods)
            if methods
            else (
                getattr(appt, "payment_method", None)
                or ("UPI" if appt.source == "ai_voice" else "Cash")
            )
        )
        collected_display = None
        collected_date = None
        collected_time = None
        if is_settled or receipts:
            total_settled += amount_collected_period
            if period_receipts:
                upi_total += sum(
                    float(receipt.amount)
                    for receipt in period_receipts
                    if receipt.method == "UPI"
                )
                cash_total += sum(
                    float(receipt.amount)
                    for receipt in period_receipts
                    if receipt.method == "Cash"
                )
            elif str(pay_method).upper() == "UPI":
                upi_total += amount_collected_period
            else:
                cash_total += amount_collected_period
            meta = appt.booking_metadata or {}
            raw_collected = meta.get("collected_at")
            if raw_collected:
                try:
                    dt = datetime.fromisoformat(raw_collected)
                    collected_date = dt.date().isoformat()
                    collected_time = dt.strftime("%I:%M %p")
                    if dt.date() == today_local:
                        collected_display = f"Today, {collected_time}"
                    elif dt.date() == today_local - timedelta(days=1):
                        collected_display = f"Yesterday, {collected_time}"
                    else:
                        collected_display = f"{dt.strftime('%d %b')}, {collected_time}"
                except Exception:
                    collected_display = (
                        meta.get("collected_at_display")
                        or appt.appointment_time
                        or "Paid"
                    )
            elif meta.get("collected_at_display"):
                collected_display = meta["collected_at_display"]
            else:
                collected_display = appt.appointment_time or "Paid"
        else:
            total_settled += amount_collected_period
            total_pending += balance_due
            upi_total += sum(
                float(receipt.amount)
                for receipt in period_receipts
                if receipt.method == "UPI"
            )
            cash_total += sum(
                float(receipt.amount)
                for receipt in period_receipts
                if receipt.method == "Cash"
            )

        meta = appt.booking_metadata or {}
        transactions.append(
            {
                "id": str(appt.id),
                "patient_name": p_name,
                "patient_phone": p_phone,
                "fee_amount": fee_amount,
                "amount_paid": amount_paid,
                "balance_due": balance_due,
                "status": "settled" if is_settled else "pending",
                "payment_method": pay_method,
                "source": appt.source,
                "appointment_date": (
                    appt.appointment_date.isoformat() if appt.appointment_date else ""
                ),
                "appointment_time": appt.appointment_time or "",
                "collected_at": collected_display,
                "collected_date": collected_date,
                "collected_time": collected_time,
                "bill_items": meta.get("bill_items", []),
            }
        )

    transactions.sort(
        key=lambda x: (
            x.get("collected_date") or x.get("appointment_date") or "",
            x.get("collected_time") or x.get("appointment_time") or "",
        ),
        reverse=True,
    )

    return {
        "org_id": str(org_id),
        "period": period,
        "total_settled": total_settled,
        "total_pending": total_pending,
        "upi_total": upi_total,
        "cash_total": cash_total,
        "currency_code": getattr(clinic_org, "currency_code", None),
        "currency_symbol": getattr(clinic_org, "currency_symbol", None),
        "transactions": transactions,
    }


async def list_visit_payment_receipts_service(
    db: AsyncSession,
    org_id: UUID,
    appointment_id: UUID,
) -> List[Dict[str, Any]]:
    appointment = await db.scalar(
        select(Appointment).where(
            Appointment.id == appointment_id, Appointment.org_id == org_id
        )
    )
    if not appointment:
        raise HTTPException(status_code=404, detail="Clinic visit not found")
    rows = (
        await db.execute(
            select(PaymentReceipt, User.full_name)
            .join(User, PaymentReceipt.received_by == User.id, isouter=True)
            .where(
                PaymentReceipt.org_id == org_id,
                PaymentReceipt.visit_id == appointment_id,
            )
            .order_by(PaymentReceipt.received_at.asc())
        )
    ).all()
    return [
        {
            "id": str(receipt.id),
            "visit_id": str(receipt.visit_id),
            "amount": float(receipt.amount),
            "method": receipt.method,
            "reference": receipt.reference,
            "received_at": receipt.received_at,
            "received_by": str(receipt.received_by) if receipt.received_by else None,
            "received_by_name": name,
        }
        for receipt, name in rows
    ]
