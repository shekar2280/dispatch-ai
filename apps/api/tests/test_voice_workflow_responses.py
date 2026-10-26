from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from livekit.agents import llm

from app.agent.clinic.tools import ClinicVoiceAgent
from app.services.voice.workflow.responses import slot_search_response


@pytest.mark.asyncio
async def test_auto_tool_continuation_uses_no_provider():
    agent = ClinicVoiceAgent("Receptionist")
    agent.state.update(pending_slot_search_response=True, last_slot_search={
        "status": "available", "doctor": "Dr. Test", "spoken_date": "tomorrow",
        "offers": [{"label": "2 PM"}],
    })
    with patch("app.services.voice.provider_budget.reserve_llm", AsyncMock()) as reserve:
        result = [chunk async for chunk in agent.llm_node(
            llm.ChatContext(), [], SimpleNamespace(tool_choice="auto"))]
    assert "2 PM" in result[0]
    reserve.assert_not_awaited()


def test_new_caller_turn_discards_stale_pending_speech():
    agent = ClinicVoiceAgent("Receptionist")
    agent.state["pending_slot_search_response"] = True
    agent.observe_caller_turn("new", "Actually, another day")
    assert "pending_slot_search_response" not in agent.state


def test_past_time_response_does_not_hide_reason():
    response = slot_search_response({"status": "available", "reason": "PAST_TIME",
        "offers": [{"label": "4 PM"}]})
    assert "already passed" in response
    assert "4 PM" in response
