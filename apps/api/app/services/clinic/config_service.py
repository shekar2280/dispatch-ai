from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.clinic_config import require_clinic_timezone


async def get_cached_clinic_context(org_id: UUID, db: AsyncSession) -> Dict[str, Any]:
    from app.services.infra.redis_cache import redis_service
    from app.models.organization import Organization
    from app.models.schedule_override import ScheduleOverride
    from sqlalchemy import select, text
    from zoneinfo import ZoneInfo

    cached = await redis_service.get_clinic_config(str(org_id))
    if cached:
        return cached

    org_res = await db.execute(
        select(Organization).where(Organization.id == org_id)
    )
    org_obj = org_res.scalar_one_or_none()
    if not org_obj:
        return {}

    tz_name = require_clinic_timezone(org_obj)
    today_date = datetime.now(ZoneInfo(tz_name)).date()
    closure_res = await db.execute(
        select(ScheduleOverride).where(
            ScheduleOverride.org_id == org_id,
            ScheduleOverride.start_date <= today_date,
            ScheduleOverride.end_date >= today_date,
        )
    )
    active_closure = closure_res.scalars().first()
    closure_notice = ""
    if active_closure:
        if active_closure.override_type == "special_hours":
            closure_notice = f"Clinic is operating on special hours today ({active_closure.title})."
        else:
            closure_notice = f"Clinic is closed from {active_closure.start_date} to {active_closure.end_date} for {active_closure.title}."

    directives = []

    config_data = {
        "org_id": str(org_obj.id),
        "name": org_obj.name,
        "city": org_obj.city,
        "address": org_obj.address,
        "phone": org_obj.phone,
        "timezone": tz_name,
        "consultation_fee": org_obj.consultation_fee,
        "currency_symbol": org_obj.currency_symbol,
        "clinic_specialty": org_obj.clinic_specialty,
        "lead_doctor_name": org_obj.lead_doctor_name,
        "emergency_deflection_phone": org_obj.emergency_deflection_phone,
        "ai_voice_name": org_obj.ai_voice_name or "priya",
        "ai_greeting_prompt": org_obj.ai_greeting_prompt,
        "closure_notice": closure_notice,
        "weekly_schedule": org_obj.weekly_schedule or {},
        "directives": directives,
    }

    await redis_service.set_clinic_config(str(org_id), config_data, ttl=3600)
    return config_data
