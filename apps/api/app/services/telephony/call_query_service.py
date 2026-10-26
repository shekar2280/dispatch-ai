from datetime import date, datetime, time, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import and_, exists, func, not_, or_, select, true

from app.models.appointment import Appointment
from app.models.call_session import VoiceCallSession
from app.models.organization import Organization
from app.services.appointments.schedule_service import clinic_timezone


def call_classification():
    session = VoiceCallSession
    booked = exists(select(Appointment.id).where(
        Appointment.org_id == session.org_id,
        Appointment.call_session_id == session.id,
        Appointment.source == "ai_voice",
    ))
    triage = func.lower(func.coalesce(session.triage_status, ""))
    outcome = func.lower(func.coalesce(session.call_outcome, ""))
    attended = func.lower(func.coalesce(session.attended_by, ""))
    complaint = func.lower(func.coalesce(session.chief_complaint, ""))
    missed = and_(not_(booked), or_(
        triage == "missed",
        outcome.in_(["missed", "caller_abandoned", "no_answer", "line_busy", "service_unavailable", "caller_silent", "speech_unrecognized"]),
        attended.contains("unattended"),
        attended.contains("missed"),
        and_(
            func.coalesce(session.duration_seconds, 0) == 0,
            func.coalesce(session.full_transcript, "") == "",
            or_(
                session.end_time.is_not(None),
                triage.in_(["ringing", "admin", "unclassified", "missed"]),
                outcome.in_(["ringing", "missed", "caller_abandoned"]),
            ),
        ),
    ))
    emergency = and_(not_(booked), or_(
        triage == "emergency",
        outcome == "emergency_deflected",
        complaint.contains("emergency"),
        complaint.contains("108"),
        complaint.contains("chest pain"),
    ))
    human = and_(not_(missed), not_(attended.contains("ai")), or_(*(attended.contains(role) for role in ["dispatcher", "officer", "human", "nurse", "doctor", "receptionist", "staff"])))
    ai = and_(not_(missed), not_(human))
    return missed, emergency, human, ai


async def load_call_page(db, org_id, limit=50, offset=0, search="", target_date: date | None = None, category="all"):
    org = await db.get(Organization, org_id)
    if not org or not org.timezone or not str(org.timezone).strip():
        raise HTTPException(status_code=422, detail="Clinic timezone is not configured")
    tz = clinic_timezone(str(org.timezone).strip())
    today = datetime.now(timezone.utc).astimezone(tz).date()
    day_start = datetime.combine(today, time.min, tzinfo=tz)
    day_end = datetime.combine(today + timedelta(days=1), time.min, tzinfo=tz)
    session = VoiceCallSession
    missed, emergency, human, ai = call_classification()
    day = and_(session.start_time >= day_start, session.start_time < day_end)
    filters = []
    if target_date:
        filters.extend([session.start_time >= datetime.combine(target_date, time.min, tzinfo=tz), session.start_time < datetime.combine(target_date + timedelta(days=1), time.min, tzinfo=tz)])
    if search.strip():
        filters.append(or_(*(func.coalesce(column, "").icontains(search.strip(), autoescape=True) for column in [session.caller_name, session.caller_phone, session.chief_complaint, session.full_transcript])))
    scope = and_(*filters) if filters else true()
    categories = {"all": true(), "missed": missed, "emergency": emergency, "ai": ai}
    selected = categories[category]
    counts = (await db.execute(select(
        func.count().label("historical"),
        func.count().filter(day).label("today"),
        func.count().filter(and_(day, missed)).label("missed_today"),
        func.count().filter(and_(day, emergency)).label("emergency_today"),
        func.count().filter(and_(day, human)).label("human_today"),
        func.count().filter(and_(day, ai)).label("ai_today"),
        *(func.count().filter(and_(scope, condition)).label(f"scope_{name}") for name, condition in categories.items()),
    ).select_from(session).where(session.org_id == org_id))).mappings().one()
    sessions = (await db.execute(select(session).where(session.org_id == org_id, scope, selected)
        .order_by(session.start_time.desc(), session.id.desc()).limit(limit).offset(offset))).scalars().all()
    booked_ids = set()
    if sessions:
        booked_ids = set((await db.execute(select(Appointment.call_session_id).where(
            Appointment.org_id == org_id, Appointment.source == "ai_voice", Appointment.call_session_id.in_([item.id for item in sessions]),
        ))).scalars().all())
    metrics = {
        "total_calls_today": counts["today"], "total_calls_historical": counts["historical"],
        "missed_calls": counts["missed_today"], "emergency_calls": counts["emergency_today"],
        "admin_calls": max(0, counts["today"] - counts["missed_today"] - counts["emergency_today"]),
        "handled_by_human": counts["human_today"], "handled_by_ai": counts["ai_today"],
    }
    return sessions, booked_ids, metrics, {name: counts[f"scope_{name}"] for name in categories}
