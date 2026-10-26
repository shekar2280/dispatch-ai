"""Regression tests for audio."""

import array
import asyncio
import io
import json
import wave
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.agent.call_context import parse_participant_call_context
from app.agent.clinic.tools import ClinicVoiceAgent
from app.services.audio.circular_audio_buffer import SAMPLE_RATE, ContiguousVADBuffer, mix_and_encode_wav
from app.services.infra.storage import sign_call_recording
from app.services.voice.country_emergency import resolve_emergency_phone


def pcm(*samples):
    return array.array("h", samples).tobytes()


def test_wav_roundtrip_is_mono_pcm_with_exact_samples():
    buffer = ContiguousVADBuffer("roundtrip")
    buffer.push_caller_frame(pcm(100, -200, 32767, -32768))
    with wave.open(io.BytesIO(buffer.generate_wav_bytes()), "rb") as audio:
        assert (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) == (1, 2, SAMPLE_RATE)
        assert audio.getnframes() == 4
        assert audio.readframes(4) == pcm(100, -200, 32767, -32768)


def test_mixing_clips_and_preserves_longer_track():
    buffer = ContiguousVADBuffer("mix")
    buffer.push_caller_frame(pcm(30000, -30000, 100))
    buffer.push_agent_staff_frame(pcm(10000, -10000))
    assert buffer.get_mixed_pcm() == pcm(32767, -32768, 100)


def test_timestamped_tracks_preserve_silence_and_alignment():
    buffer = ContiguousVADBuffer("timeline")
    buffer.push_frame(pcm(100), "caller", offset_sec=0)
    buffer.push_frame(pcm(200), "remote", offset_sec=2 / SAMPLE_RATE)
    assert buffer.get_mixed_pcm() == pcm(100, 0, 200)


def test_circular_capacity_retains_newest_samples_on_both_tracks():
    buffer = ContiguousVADBuffer("ring", max_recording_sec=4 / SAMPLE_RATE)
    buffer.push_caller_frame(pcm(1, 2, 3, 4))
    buffer.push_agent_staff_frame(pcm(10, 20, 30, 40))
    buffer.push_caller_frame(pcm(5, 6))
    assert buffer.get_mixed_pcm() == pcm(33, 44, 5, 6)
    assert len(buffer.caller_buffer) <= 8
    assert len(buffer.remote_buffer) <= 8
    assert buffer.offset_bytes == 4


def test_large_frame_is_bounded_and_empty_recording_has_no_payload():
    buffer = ContiguousVADBuffer("large", max_recording_sec=2 / SAMPLE_RATE)
    assert buffer.generate_wav_bytes() is None
    buffer.push_caller_frame(pcm(1, 2, 3, 4, 5))
    assert buffer.get_mixed_pcm() == pcm(4, 5)


def test_invalid_pcm_and_track_are_rejected():
    buffer = ContiguousVADBuffer("invalid")
    with pytest.raises(ValueError):
        buffer.push_frame(b"x")
    with pytest.raises(ValueError):
        buffer.push_frame(pcm(1), "video")


def test_sip_attributes_resolve_call_context_without_metadata():
    org_id, call_id = uuid4(), uuid4()
    context = parse_participant_call_context(
        "",
        {
            "sip.h.x-org-id": str(org_id),
            "sip.h.x-call-id": str(call_id),
            "sip.phoneNumber": "+916302296868",
        },
    )
    assert context.org_id == org_id
    assert context.call_id == call_id
    assert context.caller_phone == "+916302296868"
    assert context.stt_provider == "deepgram"


@pytest.mark.parametrize("metadata", ["", "broken", "[]", "null"])
def test_missing_or_malformed_metadata_never_provides_a_tenant(metadata):
    context = parse_participant_call_context(metadata, {})
    assert context.org_id is None
    assert context.stt_provider == "deepgram"


def test_invalid_tenant_identifier_is_rejected():
    with pytest.raises(ValueError):
        parse_participant_call_context('{"org_id":"invalid"}', {})


def test_recording_signer_rejects_other_tenants_and_public_urls():
    org_id, call_id = uuid4(), uuid4()
    for path in [f"call-recordings/{uuid4()}/{call_id}.wav", "https://example.com/audio.wav", "../audio.wav"]:
        with pytest.raises(ValueError):
            asyncio.run(sign_call_recording(path, org_id, call_id))
    with pytest.raises(ValueError):
        asyncio.run(sign_call_recording(f"call-recordings/{org_id}/{call_id}.wav", org_id, call_id, 0))


def test_resolve_emergency_phone_configured():
    assert resolve_emergency_phone("+18005550199", "US") == "+18005550199"
    assert resolve_emergency_phone("9999", "IN") == "9999"


def test_resolve_emergency_phone_by_country():
    assert resolve_emergency_phone(None, "US") == "911"
    assert resolve_emergency_phone(None, "CA") == "911"
    assert resolve_emergency_phone(None, "GB") == "999"
    assert resolve_emergency_phone(None, "UK") == "999"
    assert resolve_emergency_phone(None, "IN") == "102"
    assert resolve_emergency_phone(None, "AU") == "000"
    assert resolve_emergency_phone(None, "ZZ") == ""
    assert resolve_emergency_phone(None, None) == ""


@pytest.mark.asyncio
async def test_deflect_emergency():
    org_id = uuid4()
    agent = ClinicVoiceAgent(
        system_prompt="Instruction",
        org_id=org_id,
        caller_phone="+15551234567",
        emergency_phone="911",
    )
    agent.call_session_id = uuid4()

    with patch(
        "app.services.infra.websocket_manager.ws_manager.broadcast_to_org", new_callable=AsyncMock
    ) as mock_broadcast:
        instruction = await agent.deflect_emergency("Severe chest pain and difficulty breathing")

        assert agent.outcome_tracker["call_outcome"] == "emergency_deflected"
        assert agent.outcome_tracker["chief_complaint"] == "Severe chest pain and difficulty breathing"
        assert agent.state["call_completed"] is True
        assert "911" in instruction
        assert "nearest emergency room" in instruction

        mock_broadcast.assert_awaited_once()
        args = mock_broadcast.await_args[0]
        assert args[0] == str(org_id)
        assert args[1]["event"] == "EMERGENCY_SOS_ALERT"
        assert args[1]["chief_complaint"] == "Severe chest pain and difficulty breathing"
        assert args[1]["emergency_phone"] == "911"


@pytest.mark.asyncio
async def test_transfer_to_reception_staff_absent():
    room = MagicMock()
    room.remote_participants = {}
    agent = ClinicVoiceAgent(
        system_prompt="Instruction",
        org_id=uuid4(),
        caller_phone="+15551234567",
        room=room,
    )

    msg = await agent.transfer_to_reception("Billing clarification")
    assert agent.outcome_tracker["call_outcome"] == "staff_transfer_unavailable"
    assert "unavailable for a live transfer" in msg
    assert "callback" in msg


@pytest.mark.asyncio
async def test_transfer_to_reception_staff_present():
    room = MagicMock()
    staff_participant = MagicMock()
    staff_participant.identity = "staff_nurse_jane"
    staff_participant.metadata = ""
    room.remote_participants = {"p1": staff_participant}
    room.local_participant.publish_data = AsyncMock()

    agent = ClinicVoiceAgent(
        system_prompt="Instruction",
        org_id=uuid4(),
        caller_phone="+15551234567",
        room=room,
    )
    agent.call_session_id = uuid4()

    msg = await agent.transfer_to_reception("Needs human receptionist")
    assert agent.outcome_tracker["call_outcome"] == "transferred_to_staff"
    assert agent.state["agent_paused"] is True
    assert "Connecting you with our reception desk" in msg
    room.local_participant.publish_data.assert_awaited_once()
    payload = json.loads(room.local_participant.publish_data.await_args[0][0].decode("utf-8"))
    assert payload["type"] == "staff_transfer_requested"


@pytest.mark.asyncio
async def test_llm_node_gated_when_agent_paused():
    agent = ClinicVoiceAgent(
        system_prompt="Instruction",
        org_id=uuid4(),
        caller_phone="+15551234567",
    )
    agent.state["agent_paused"] = True

    chat_ctx = MagicMock()
    chunks = []
    async for chunk in agent.llm_node(chat_ctx, [], MagicMock()):
        chunks.append(chunk)

    assert len(chunks) == 0


def test_circular_audio_buffer_snapshot_isolation():
    buf = ContiguousVADBuffer("test_session")
    pcm_frame_a = b"\x01\x00" * 8000
    pcm_frame_b = b"\x02\x00" * 8000

    buf.push_caller_frame(pcm_frame_a)
    buf.push_agent_staff_frame(pcm_frame_b)

    snap_a, snap_b = buf.snapshot_buffers()
    assert snap_a == pcm_frame_a
    assert snap_b == pcm_frame_b

    buf.push_caller_frame(b"\x03\x00" * 1000)
    assert snap_a == pcm_frame_a
    assert len(buf.caller_buffer) == len(pcm_frame_a) + 2000

    wav = mix_and_encode_wav(snap_a, snap_b)
    assert wav is not None
    assert wav.startswith(b"RIFF")
