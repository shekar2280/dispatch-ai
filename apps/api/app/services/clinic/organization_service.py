import hashlib
import logging
from typing import Optional, List
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.organization import Organization
from app.models.schedule_override import ScheduleOverride
from app.schemas.schedule_override import ScheduleOverrideCreate, ScheduleOverrideResponse
from app.core.security import invalidate_org_tenant_cache
from app.services.infra.redis_cache import redis_service
from app.core.phone_utils import normalize_phone_e164

logger = logging.getLogger(__name__)


async def get_organization_by_id(db: AsyncSession, org_id: UUID) -> Organization:
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


async def get_organization_landmarks(db: AsyncSession, org_id: UUID) -> list:
    org = await get_organization_by_id(db, org_id)
    return org.landmarks or []


async def update_organization_landmarks(
    db: AsyncSession,
    org_id: UUID,
    landmarks: list,
    operational_center_name: Optional[str] = None,
    service_radius_km: Optional[float] = None,
) -> list:
    org = await get_organization_by_id(db, org_id)
    org.landmarks = landmarks
    if operational_center_name is not None:
        org.operational_center_name = operational_center_name
    if service_radius_km is not None:
        org.service_radius_km = str(service_radius_km)
    await db.commit()
    await db.refresh(org)
    return org.landmarks or []


async def _synthesize_and_publish_greeting(org_id: UUID, version: int, content_hash: str, voice_id: str, text: str):
    import os
    import tempfile
    from app.services.audio.tts_service import generate_voice_speech
    from app.services.infra.storage import upload_greeting_bytes_to_supabase
    from app.core.database import AsyncSessionLocal
    from sqlalchemy.orm.attributes import flag_modified

    try:
        audio_bytes = await generate_voice_speech(text, voice_id=voice_id)
        if not audio_bytes or len(audio_bytes) < 100:
            return
        storage_filename = f"{org_id}_{voice_id}_{content_hash}"
        saved_path = await upload_greeting_bytes_to_supabase(storage_filename, audio_bytes)
        cache_dir = os.path.join(tempfile.gettempdir(), "greetings")
        os.makedirs(cache_dir, exist_ok=True)
        local_cache_path = os.path.join(cache_dir, f"{org_id}_{content_hash}.mp3")
        with open(local_cache_path, "wb") as f:
            f.write(audio_bytes)

        async with AsyncSessionLocal() as session:
            current_org = await session.get(Organization, org_id)
            if not current_org:
                return
            current_settings = dict(current_org.voice_ai_settings or {})
            if int(current_settings.get("settings_version", 0)) == version:
                asset = dict(current_settings.get("greeting_asset") or {})
                asset["status"] = "ready"
                asset["audio_url"] = saved_path or local_cache_path
                current_settings["greeting_asset"] = asset
                current_org.voice_ai_settings = current_settings
                flag_modified(current_org, "voice_ai_settings")
                await session.commit()
    except Exception as e:
        logger.error("Greeting publication failed: %s", type(e).__name__)


async def update_organization_settings(
    db: AsyncSession,
    org_id: UUID,
    update,
) -> Organization:
    import asyncio
    from sqlalchemy.orm.attributes import flag_modified
    from app.services.audio.tts_service import resolve_voice

    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    voice_settings = dict(org.voice_ai_settings or {})
    current_version = int(voice_settings.get("settings_version", 1))

    if getattr(update, "settings_version", None) is not None:
        if update.settings_version != current_version:
            raise HTTPException(
                status_code=409,
                detail=f"Settings conflict: expected version {update.settings_version}, but database is at version {current_version}.",
            )

    if update.ai_voice_name is not None or update.voice_id is not None:
        chosen = update.ai_voice_name or update.voice_id
        try:
            canonical_voice = resolve_voice(chosen, strict=True)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        org.ai_voice_name = canonical_voice
        org.voice_id = canonical_voice

    if update.timezone is not None:
        org.timezone = update.timezone
    if update.name is not None:
        org.name = update.name
    if update.city is not None:
        org.city = update.city
    if update.address is not None:
        org.address = update.address
    if update.country is not None:
        org.country = update.country
    if update.country_code is not None:
        org.country_code = update.country_code
    if update.currency_code is not None:
        org.currency_code = update.currency_code
    if update.currency_symbol is not None:
        org.currency_symbol = update.currency_symbol
    if update.sector is not None:
        org.sector = update.sector
    if update.system_prompt is not None:
        org.system_prompt = update.system_prompt
    if update.custom_greeting is not None:
        org.custom_greeting = update.custom_greeting
    if update.ai_greeting_prompt is not None:
        org.ai_greeting_prompt = update.ai_greeting_prompt
    if update.ai_language_mode is not None:
        org.ai_language_mode = update.ai_language_mode
    if update.slot_duration_minutes is not None:
        org.slot_duration_minutes = update.slot_duration_minutes
    if update.working_hours is not None:
        org.working_hours = update.working_hours
    if update.closure_notice is not None:
        org.closure_notice = update.closure_notice
    if update.operational_center_name is not None:
        org.operational_center_name = update.operational_center_name
    if update.service_radius_km is not None:
        org.service_radius_km = update.service_radius_km
    if update.landmarks is not None:
        org.landmarks = update.landmarks
    if update.call_routing_mode is not None:
        org.call_routing_mode = update.call_routing_mode
    phone_to_check = None
    if update.phone is not None:
        phone_to_check = update.phone
    elif update.hotline is not None:
        phone_to_check = update.hotline

    if phone_to_check is not None:
        country = (update.country_code or org.country_code or "").strip().upper() or None
        norm = normalize_phone_e164(phone_to_check, default_country=country)
        if not norm.is_valid or not norm.e164_phone:
            raise HTTPException(
                status_code=422,
                detail="Invalid phone number format",
            )
        dup = await db.execute(
            select(Organization.id).where(
                Organization.phone == norm.e164_phone,
                Organization.id != org.id,
            )
        )
        if dup.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail="Phone number already registered by another organization",
            )
        org.phone = norm.e164_phone
        org.hotline = norm.e164_phone
    if update.clinic_specialty is not None:
        org.clinic_specialty = update.clinic_specialty
    if update.lead_doctor_name is not None:
        org.lead_doctor_name = update.lead_doctor_name
    if update.consultation_fee is not None:
        org.consultation_fee = update.consultation_fee
    if update.visit_charge_types is not None or update.billing_catalog is not None:
        if update.visit_charge_types is not None:
            for item in update.visit_charge_types:
                if (
                    not str(item.get("name", "")).strip()
                    or float(item.get("fee", -1)) < 0
                ):
                    raise HTTPException(
                        status_code=422,
                        detail="Visit charges need a name and a non-negative fee",
                    )
        if update.billing_catalog is not None:
            for item in update.billing_catalog:
                if (
                    not str(item.get("name", "")).strip()
                    or float(item.get("unit_price", -1)) < 0
                ):
                    raise HTTPException(
                        status_code=422,
                        detail="Catalog items need a name and a non-negative unit price",
                    )
                if item.get("category") not in {"medicine", "procedure", "other"}:
                    raise HTTPException(
                        status_code=422,
                        detail="Catalog item category must be medicine, procedure, or other",
                    )
        booking = dict(org.booking_settings or {})
        if update.visit_charge_types is not None:
            booking["visit_charge_types"] = update.visit_charge_types
        if update.billing_catalog is not None:
            booking["billing_catalog"] = update.billing_catalog
        org.booking_settings = booking
        flag_modified(org, "booking_settings")
        charge_types = booking.get("visit_charge_types", [])
        standard = next(
            (item for item in charge_types if item.get("id") == "standard"),
            charge_types[0] if charge_types else None,
        )
        if standard is not None:
            org.consultation_fee = int(standard.get("fee", org.consultation_fee or 0))
    if update.default_slot_duration_minutes is not None:
        org.default_slot_duration_minutes = update.default_slot_duration_minutes
    if update.emergency_deflection_phone is not None:
        org.emergency_deflection_phone = update.emergency_deflection_phone
    if update.ai_voice_role is not None:
        org.ai_voice_role = update.ai_voice_role
    if update.greeting_audio_url is not None:
        org.greeting_audio_url = update.greeting_audio_url
    if update.weekly_schedule is not None:
        org.weekly_schedule = update.weekly_schedule
    if update.slot_buffer_minutes is not None:
        org.slot_buffer_minutes = update.slot_buffer_minutes
    if update.max_daily_patients is not None:
        org.max_daily_patients = update.max_daily_patients

    new_version = current_version + 1
    voice_settings = dict(org.voice_ai_settings or {})
    voice_settings["settings_version"] = new_version

    greeting_job = None
    raw_text = (org.ai_greeting_prompt or org.custom_greeting or "").strip()
    voice_to_use = org.ai_voice_name or "aura-asteria-en"
    if raw_text:
        resolved_text = raw_text.replace("{{clinic_name}}", org.name).replace(
            "{clinic_name}", org.name
        )
        content_hash = hashlib.sha256(
            f"{voice_to_use}:{resolved_text.strip()}".encode()
        ).hexdigest()[:16]
        existing_asset = dict(voice_settings.get("greeting_asset") or {})
        if existing_asset.get("content_hash") == content_hash and existing_asset.get("status") == "ready":
            existing_asset["version"] = new_version
            voice_settings["greeting_asset"] = existing_asset
        else:
            voice_settings["greeting_asset"] = {
                "version": new_version,
                "content_hash": content_hash,
                "voice_id": voice_to_use,
                "status": "pending",
                "text": resolved_text,
                "codec": "mp3",
                "audio_url": None,
            }
            greeting_job = (org.id, new_version, content_hash, voice_to_use, resolved_text)

    org.voice_ai_settings = voice_settings
    flag_modified(org, "voice_ai_settings")

    await db.commit()
    await db.refresh(org)
    await invalidate_org_tenant_cache(org.id)
    await redis_service.invalidate_clinic_config(str(org_id))

    if greeting_job:
        asyncio.create_task(_synthesize_and_publish_greeting(*greeting_job))

    return org


async def delete_organization_service(db: AsyncSession, org_id: UUID):
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    await db.delete(org)
    await db.commit()
    return {"status": "success", "message": "Practice account permanently purged"}


async def list_org_closures_service(db: AsyncSession, target_org_id: UUID) -> List[ScheduleOverride]:
    res = await db.execute(
        select(ScheduleOverride)
        .where(ScheduleOverride.org_id == target_org_id)
        .order_by(ScheduleOverride.start_date.asc())
    )
    return list(res.scalars().all())


async def create_org_closure_service(
    db: AsyncSession, target_org_id: UUID, body: ScheduleOverrideCreate
) -> ScheduleOverride:
    org = await db.get(Organization, target_org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    if body.end_date < body.start_date:
        raise HTTPException(
            status_code=400, detail="End date cannot be before start date"
        )
    override_type = body.override_type or "vacation"
    is_available = (
        body.is_available
        if body.is_available is not None
        else (override_type == "special_hours")
    )
    closure = ScheduleOverride(
        org_id=target_org_id,
        doctor_id=body.doctor_id,
        title=body.title,
        override_type=override_type,
        is_available=is_available,
        start_date=body.start_date,
        end_date=body.end_date,
        custom_hours=body.custom_hours,
        reason=body.reason,
        emergency_phone=body.emergency_phone,
    )
    db.add(closure)
    await db.commit()
    await db.refresh(closure)
    return closure


async def delete_org_closure_service(
    db: AsyncSession, target_org_id: UUID, closure_id: UUID
):
    res = await db.execute(
        select(ScheduleOverride).where(
            ScheduleOverride.id == closure_id, ScheduleOverride.org_id == target_org_id
        )
    )
    closure = res.scalar_one_or_none()
    if not closure:
        raise HTTPException(status_code=404, detail="Closure record not found")
    await db.delete(closure)
    await db.commit()
    return {"status": "success", "message": "Closure record deleted"}


async def update_org_closure_service(
    db: AsyncSession, target_org_id: UUID, closure_id: UUID, body: ScheduleOverrideCreate
) -> ScheduleOverride:
    result = await db.execute(
        select(ScheduleOverride).where(
            ScheduleOverride.id == closure_id, ScheduleOverride.org_id == target_org_id
        )
    )
    closure = result.scalar_one_or_none()
    if not closure:
        raise HTTPException(status_code=404, detail="Closure record not found")
    if body.end_date < body.start_date:
        raise HTTPException(status_code=400, detail="End date cannot be before start date")
    for field, value in body.model_dump().items():
        setattr(closure, field, value)
    closure.override_type = body.override_type or "vacation"
    closure.is_available = body.is_available if body.is_available is not None else closure.override_type == "special_hours"
    await db.commit()
    await db.refresh(closure)
    return closure
