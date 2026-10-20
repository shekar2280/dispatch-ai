from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from uuid import UUID
import hashlib

from app.core.database import get_db
from app.core.security import get_current_tenant_org
from app.schemas.schedule_override import ScheduleOverrideCreate, ScheduleOverrideResponse
from app.services.clinic.organization_service import (
    get_organization_by_id,
    update_organization_settings,
    delete_organization_service,
    list_org_closures_service,
    create_org_closure_service,
    delete_org_closure_service,
    update_org_closure_service,
)

router = APIRouter()


class OrgResponse(BaseModel):
    id: UUID
    name: str
    city: Optional[str] = None
    address: Optional[str] = None
    timezone: Optional[str] = None
    country: Optional[str] = None
    country_code: Optional[str] = None
    currency_code: Optional[str] = None
    currency_symbol: Optional[str] = None
    sector: Optional[str] = None
    clinic_specialty: Optional[str] = None
    lead_doctor_name: Optional[str] = None
    consultation_fee: Optional[int] = None
    visit_charge_types: list[dict] = []
    billing_catalog: list[dict] = []
    default_slot_duration_minutes: Optional[int] = None
    emergency_deflection_phone: Optional[str] = None
    ai_voice_role: Optional[str] = None
    system_prompt: Optional[str] = None
    custom_greeting: Optional[str] = None
    ai_greeting_prompt: Optional[str] = None
    ai_voice_name: Optional[str] = None
    ai_language_mode: Optional[str] = None
    voice_id: Optional[str] = None
    slot_duration_minutes: Optional[str] = None
    working_hours: Optional[dict] = None
    closure_notice: Optional[str] = None
    operational_center_name: Optional[str] = None
    service_radius_km: Optional[str] = None
    landmarks: Optional[list] = None
    call_routing_mode: Optional[str] = None
    hotline: Optional[str] = None
    phone: Optional[str] = None
    greeting_audio_url: Optional[str] = None
    weekly_schedule: Optional[dict] = None
    slot_buffer_minutes: Optional[int] = None
    max_daily_patients: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class OrgConfigUpdate(BaseModel):
    timezone: Optional[str] = None
    name: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    country: Optional[str] = None
    country_code: Optional[str] = None
    currency_code: Optional[str] = None
    currency_symbol: Optional[str] = None
    sector: Optional[str] = None
    clinic_specialty: Optional[str] = None
    lead_doctor_name: Optional[str] = None
    consultation_fee: Optional[int] = None
    visit_charge_types: Optional[list[dict]] = None
    billing_catalog: Optional[list[dict]] = None
    default_slot_duration_minutes: Optional[int] = None
    emergency_deflection_phone: Optional[str] = None
    ai_voice_role: Optional[str] = None
    system_prompt: Optional[str] = None
    custom_greeting: Optional[str] = None
    ai_greeting_prompt: Optional[str] = None
    ai_voice_name: Optional[str] = None
    ai_language_mode: Optional[str] = None
    voice_id: Optional[str] = None
    slot_duration_minutes: Optional[str] = None
    working_hours: Optional[dict] = None
    closure_notice: Optional[str] = None
    operational_center_name: Optional[str] = None
    service_radius_km: Optional[str] = None
    landmarks: Optional[list] = None
    call_routing_mode: Optional[str] = None
    hotline: Optional[str] = None
    phone: Optional[str] = None
    greeting_audio_url: Optional[str] = None
    weekly_schedule: Optional[dict] = None
    slot_buffer_minutes: Optional[int] = None
    max_daily_patients: Optional[int] = None
    settings_version: Optional[int] = None


class VoicePreviewRequest(BaseModel):
    text: str = Field(min_length=1, max_length=400)
    voice_id: Optional[str] = "aura-asteria-en"


_tts_preview_cache: dict[str, bytes] = {}
_TTS_PREVIEW_CACHE_MAX = 100


@router.get("/voice-catalog")
async def get_voice_catalog():
    from app.services.audio.tts_service import SUPPORTED_VOICE_CATALOG
    return SUPPORTED_VOICE_CATALOG


@router.get("/me", response_model=OrgResponse)
async def get_my_org(
    current_org_id: UUID = Depends(get_current_tenant_org),
    db: AsyncSession = Depends(get_db),
):
    return await get_organization_by_id(db, current_org_id)


@router.get("/{org_id}", response_model=OrgResponse)
async def get_org(
    org_id: UUID,
    current_org_id: UUID = Depends(get_current_tenant_org),
    db: AsyncSession = Depends(get_db),
):
    if current_org_id != org_id:
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Cannot access resources for another clinic organization",
        )
    return await get_organization_by_id(db, org_id)


@router.patch("/{org_id}", response_model=OrgResponse)
async def update_organization(
    org_id: UUID,
    update: OrgConfigUpdate,
    current_org_id: UUID = Depends(get_current_tenant_org),
    db: AsyncSession = Depends(get_db),
):
    if current_org_id != org_id:
        raise HTTPException(
            status_code=403, detail="Forbidden: Cross-tenant update denied"
        )
    return await update_organization_settings(db, org_id, update)


@router.delete("/{org_id}")
async def delete_organization(
    org_id: UUID,
    current_org_id: UUID = Depends(get_current_tenant_org),
    db: AsyncSession = Depends(get_db),
):
    if current_org_id != org_id:
        raise HTTPException(
            status_code=403, detail="Forbidden: Cross-tenant deletion denied"
        )
    return await delete_organization_service(db, org_id)


@router.post("/voice-preview")
async def preview_voice_greeting(
    req: VoicePreviewRequest,
    _: UUID = Depends(get_current_tenant_org),
):
    from app.services.audio.tts_service import generate_voice_speech, resolve_voice

    try:
        target_voice = resolve_voice(req.voice_id or "aura-asteria-en", strict=True)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    cache_key = hashlib.sha256(
        f"{target_voice}:{req.text.strip()}".encode()
    ).hexdigest()

    if cache_key in _tts_preview_cache:
        cached_data = _tts_preview_cache[cache_key]
        mtype = "audio/wav" if cached_data.startswith(b"RIFF") else "audio/mpeg"
        return Response(content=cached_data, media_type=mtype)
    try:
        audio_bytes = await generate_voice_speech(req.text, voice_id=target_voice)
        _tts_preview_cache[cache_key] = audio_bytes
        while len(_tts_preview_cache) > _TTS_PREVIEW_CACHE_MAX:
            _tts_preview_cache.pop(next(iter(_tts_preview_cache)))
        mtype = "audio/wav" if audio_bytes.startswith(b"RIFF") else "audio/mpeg"
        return Response(content=audio_bytes, media_type=mtype)
    except HTTPException:
        raise
    except Exception:
        import logging
        logging.getLogger(__name__).exception("voice_preview_generation_failed")
        raise HTTPException(status_code=500, detail="Voice preview generation failed.")


@router.get("/me/closures", response_model=list[ScheduleOverrideResponse])
@router.get("/{org_id}/closures", response_model=list[ScheduleOverrideResponse])
async def list_org_closures(
    org_id: Optional[UUID] = None,
    current_org_id: UUID = Depends(get_current_tenant_org),
    db: AsyncSession = Depends(get_db),
):
    target_org_id = org_id or current_org_id
    if current_org_id != target_org_id:
        raise HTTPException(
            status_code=403, detail="Forbidden: Cross-tenant access denied"
        )
    return await list_org_closures_service(db, target_org_id)


@router.post("/me/closures", response_model=ScheduleOverrideResponse)
@router.post("/{org_id}/closures", response_model=ScheduleOverrideResponse)
async def create_org_closure(
    body: ScheduleOverrideCreate,
    org_id: Optional[UUID] = None,
    current_org_id: UUID = Depends(get_current_tenant_org),
    db: AsyncSession = Depends(get_db),
):
    target_org_id = org_id or current_org_id
    if current_org_id != target_org_id:
        raise HTTPException(
            status_code=403, detail="Forbidden: Cross-tenant operation denied"
        )
    return await create_org_closure_service(db, target_org_id, body)


@router.delete("/me/closures/{closure_id}")
@router.delete("/{org_id}/closures/{closure_id}")
async def delete_org_closure(
    closure_id: UUID,
    org_id: Optional[UUID] = None,
    current_org_id: UUID = Depends(get_current_tenant_org),
    db: AsyncSession = Depends(get_db),
):
    target_org_id = org_id or current_org_id
    if current_org_id != target_org_id:
        raise HTTPException(
            status_code=403, detail="Forbidden: Cross-tenant operation denied"
        )
    return await delete_org_closure_service(db, target_org_id, closure_id)


@router.put("/me/closures/{closure_id}", response_model=ScheduleOverrideResponse)
@router.put("/{org_id}/closures/{closure_id}", response_model=ScheduleOverrideResponse)
async def update_org_closure(
    closure_id: UUID,
    body: ScheduleOverrideCreate,
    org_id: Optional[UUID] = None,
    current_org_id: UUID = Depends(get_current_tenant_org),
    db: AsyncSession = Depends(get_db),
):
    target_org_id = org_id or current_org_id
    if current_org_id != target_org_id:
        raise HTTPException(status_code=403, detail="Forbidden: Cross-tenant operation denied")
    return await update_org_closure_service(db, target_org_id, closure_id, body)
