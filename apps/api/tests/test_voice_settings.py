"""Regression tests for voice settings."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.agent.agent_prompts import get_system_prompt
from app.agent.prompt_builder import build_system_prompt
from app.api.v1.organization import OrgConfigUpdate, OrgResponse
from app.models.organization import Organization
from app.services.audio.tts_service import SUPPORTED_VOICE_CATALOG, SUPPORTED_VOICE_IDS, resolve_voice
from app.services.clinic.organization_service import update_organization_settings


def test_organization_model_columns():
    org = Organization(
        id=uuid4(),
        name="Apex Clinic",
        ai_greeting_prompt="Welcome to Apex Clinic. How can I help you?",
        custom_greeting="Apex Clinic greeting",
        ai_voice_name="alloy",
        ai_language_mode="en_hi_bilingual",
    )
    assert org.ai_greeting_prompt == "Welcome to Apex Clinic. How can I help you?"
    assert org.custom_greeting == "Apex Clinic greeting"
    assert org.ai_voice_name == "alloy"
    assert org.ai_language_mode == "en_hi_bilingual"


def test_pydantic_org_schemas():
    data = {
        "id": uuid4(),
        "name": "Apex Clinic",
        "timezone": "Asia/Kolkata",
        "ai_greeting_prompt": "Hello from Apex Doctor Clinic!",
        "custom_greeting": "Short greeting",
        "ai_voice_name": "nova",
        "ai_language_mode": "en_hi_bilingual",
    }
    resp = OrgResponse(**data)
    assert resp.ai_greeting_prompt == "Hello from Apex Doctor Clinic!"
    assert resp.ai_voice_name == "nova"

    update_payload = OrgConfigUpdate(
        ai_greeting_prompt="Updated custom greeting",
        ai_voice_name="shimmer",
    )
    assert update_payload.ai_greeting_prompt == "Updated custom greeting"
    assert update_payload.ai_voice_name == "shimmer"


def test_get_system_prompt_custom_greeting():
    custom_text = "Good morning! Dr. Mehta's office. How can I assist you today?"
    prompt = get_system_prompt(
        clinic_name="Mehta Clinic",
        tz_name="Asia/Kolkata",
        custom_greeting=custom_text,
    )
    assert custom_text in prompt
    assert f'ALWAYS greet neutrally using your opening script: "{custom_text}"' in prompt


def test_get_system_prompt_default_fallback():
    prompt = get_system_prompt(
        clinic_name="City Hospital",
        tz_name="Asia/Kolkata",
        custom_greeting=None,
    )
    assert (
        'ALWAYS greet neutrally: "Hello! Thank you for calling City Hospital. How can I assist you today?".' in prompt
    )


def test_build_system_prompt_integration():
    import asyncio

    async def _runner():
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_cursor

        custom_text = "Hello! Sharma Orthopedics. Are you calling to book a consultation?"
        prompt = await build_system_prompt(
            db=mock_db,
            org_id=uuid4(),
            clinic_name="Sharma Orthopedics",
            tz_name="Asia/Kolkata",
            caller_name="Priya",
            caller_phone="+919876543210",
            closure_notice=None,
            available_dispatchers=1,
            custom_greeting=custom_text,
        )
        assert custom_text in prompt
        assert "CLINIC VOICE RECEPTIONIST & APPOINTMENT PROTOCOL" in prompt

    asyncio.run(_runner())


def test_greeting_resolution_hierarchy():
    org_mock = MagicMock()
    org_mock.name = "Apollo Clinic"
    org_mock.ai_greeting_prompt = "Custom AI greeting from doctor settings."
    org_mock.custom_greeting = "Legacy greeting."

    greeting = (
        getattr(org_mock, "ai_greeting_prompt", None)
        or getattr(org_mock, "custom_greeting", None)
        or f"Hello! Thank you for calling {org_mock.name}. How can I assist you today?"
    ).strip()
    assert greeting == "Custom AI greeting from doctor settings."

    org_mock.ai_greeting_prompt = None
    greeting_fallback_legacy = (
        getattr(org_mock, "ai_greeting_prompt", None)
        or getattr(org_mock, "custom_greeting", None)
        or f"Hello! Thank you for calling {org_mock.name}. How can I assist you today?"
    ).strip()
    assert greeting_fallback_legacy == "Legacy greeting."

    org_mock.custom_greeting = None
    greeting_default = (
        getattr(org_mock, "ai_greeting_prompt", None)
        or getattr(org_mock, "custom_greeting", None)
        or f"Hello! Thank you for calling {org_mock.name}. How can I assist you today?"
    ).strip()
    assert greeting_default == "Hello! Thank you for calling Apollo Clinic. How can I assist you today?"


def test_voice_preview_endpoint():
    import asyncio
    from unittest.mock import patch

    from app.api.v1.organization import VoicePreviewRequest, preview_voice_greeting

    async def _runner():
        req = VoicePreviewRequest(
            text="Hello! Thank you for calling Dr. Roy's clinic.",
            voice_id="priya",
        )
        with patch("app.services.audio.tts_service.generate_voice_speech", new_callable=AsyncMock) as mock_tts:
            mock_tts.return_value = b"MOCK_MP3_AUDIO_STREAM_BYTES"
            res = await preview_voice_greeting(req)
            assert res.media_type == "audio/mpeg"
            assert res.body == b"MOCK_MP3_AUDIO_STREAM_BYTES"
            mock_tts.assert_called_once_with(
                "Hello! Thank you for calling Dr. Roy's clinic.",
                voice_id="aura-asteria-en",
            )

            res2 = await preview_voice_greeting(req)
            assert res2.media_type == "audio/mpeg"
            assert res2.body == b"MOCK_MP3_AUDIO_STREAM_BYTES"
            assert mock_tts.call_count == 1

    asyncio.run(_runner())


def test_voice_catalog_lists_supported_deepgram_voices():
    assert len(SUPPORTED_VOICE_CATALOG) >= 5
    ids = {item["id"] for item in SUPPORTED_VOICE_CATALOG}
    assert "aura-asteria-en" in ids
    assert "aura-luna-en" in ids
    assert "aura-athena-en" in ids
    assert "aura-arcas-en" in ids
    assert "aura-zeus-en" in ids
    for voice in SUPPORTED_VOICE_CATALOG:
        assert voice["provider"] == "deepgram"
        assert voice["model"] == "aura"


def test_resolve_voice_maps_aliases_and_rejects_unsupported():
    assert resolve_voice("priya") == "aura-asteria-en"
    assert resolve_voice("gemini-aoede") == "aura-asteria-en"
    assert resolve_voice("gemini-kore") == "aura-athena-en"
    assert resolve_voice("rohan") == "aura-arcas-en"
    assert resolve_voice("meena") == "aura-luna-en"
    assert resolve_voice("aura-zeus-en") == "aura-zeus-en"

    with pytest.raises(ValueError):
        resolve_voice("fake-voice-id", strict=True)


@pytest.mark.asyncio
async def test_optimistic_concurrency_rejects_stale_version_with_409():
    org_id = uuid4()
    org = MagicMock()
    org.id = org_id
    org.voice_ai_settings = {"settings_version": 3}
    db = AsyncMock()
    db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=org))

    update = SimpleNamespace(
        settings_version=2,
        ai_voice_name=None,
        voice_id=None,
        timezone=None,
        name=None,
        city=None,
        address=None,
        country=None,
        country_code=None,
        currency_code=None,
        currency_symbol=None,
        sector=None,
        system_prompt=None,
        custom_greeting=None,
        ai_greeting_prompt=None,
        ai_language_mode=None,
        slot_duration_minutes=None,
        working_hours=None,
        closure_notice=None,
        operational_center_name=None,
        service_radius_km=None,
        landmarks=None,
        call_routing_mode=None,
        phone=None,
        hotline=None,
        clinic_specialty=None,
        lead_doctor_name=None,
        consultation_fee=None,
        visit_charge_types=None,
        billing_catalog=None,
        default_slot_duration_minutes=None,
        emergency_deflection_phone=None,
        ai_voice_role=None,
        greeting_audio_url=None,
        weekly_schedule=None,
        slot_buffer_minutes=None,
        max_daily_patients=None,
    )

    with pytest.raises(HTTPException) as exc_info:
        await update_organization_settings(db, org_id, update)
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_update_settings_increments_version_and_sets_outbox_asset():
    org_id = uuid4()
    org = MagicMock()
    org.id = org_id
    org.name = "City Health"
    org.voice_ai_settings = {"settings_version": 2}
    org.ai_greeting_prompt = "Hello from {clinic_name}"
    org.custom_greeting = None
    org.ai_voice_name = "aura-asteria-en"
    db = AsyncMock()
    db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=org))

    update = SimpleNamespace(
        settings_version=2,
        ai_voice_name="aura-luna-en",
        voice_id=None,
        timezone=None,
        name=None,
        city=None,
        address=None,
        country=None,
        country_code=None,
        currency_code=None,
        currency_symbol=None,
        sector=None,
        system_prompt=None,
        custom_greeting=None,
        ai_greeting_prompt=None,
        ai_language_mode=None,
        slot_duration_minutes=None,
        working_hours=None,
        closure_notice=None,
        operational_center_name=None,
        service_radius_km=None,
        landmarks=None,
        call_routing_mode=None,
        phone=None,
        hotline=None,
        clinic_specialty=None,
        lead_doctor_name=None,
        consultation_fee=None,
        visit_charge_types=None,
        billing_catalog=None,
        default_slot_duration_minutes=None,
        emergency_deflection_phone=None,
        ai_voice_role=None,
        greeting_audio_url=None,
        weekly_schedule=None,
        slot_buffer_minutes=None,
        max_daily_patients=None,
    )

    with (
        patch("app.services.clinic.organization_service.invalidate_org_tenant_cache", new_callable=AsyncMock),
        patch(
            "app.services.clinic.organization_service.redis_service.invalidate_clinic_config", new_callable=AsyncMock
        ),
        patch(
            "app.services.clinic.organization_service._synthesize_and_publish_greeting", new_callable=AsyncMock
        ) as mock_synth,
    ):
        result = await update_organization_settings(db, org_id, update)

    assert result.voice_ai_settings["settings_version"] == 3
    asset = result.voice_ai_settings["greeting_asset"]
    assert asset["version"] == 3
    assert asset["voice_id"] == "aura-luna-en"
    assert asset["status"] == "pending"
    assert "City Health" in asset["text"]


@pytest.mark.asyncio
async def test_update_settings_rejects_unsupported_voice_with_422():
    org_id = uuid4()
    org = MagicMock()
    org.id = org_id
    org.voice_ai_settings = {"settings_version": 1}
    db = AsyncMock()
    db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=org))

    update = SimpleNamespace(settings_version=1, ai_voice_name="invalid-voice-xyz", voice_id=None)

    with pytest.raises(HTTPException) as exc_info:
        await update_organization_settings(db, org_id, update)
    assert exc_info.value.status_code == 422
