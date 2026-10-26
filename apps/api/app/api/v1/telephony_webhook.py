from typing import Optional
from fastapi import APIRouter, Form, Query, Request, Response, Depends
from app.core.database import AsyncSessionLocal
from app.core.telephony_security import validate_twilio_request
from app.services.telephony.twilio_service import (
    handle_twilio_inbound,
    handle_twilio_dial_status,
    handle_twilio_sip_status,
    handle_twilio_status,
)

router = APIRouter()


@router.post("/twilio/inbound")
async def handle_inbound_voice(
    request: Request,
    From: Optional[str] = Form(None),
    To: Optional[str] = Form(None),
    CallSid: Optional[str] = Form(None),
    CallerName: Optional[str] = Form(None),
    _valid: bool = Depends(validate_twilio_request),
):
    return await handle_twilio_inbound(
        From=From,
        To=To,
        CallSid=CallSid,
        CallerName=CallerName,
        session_factory=AsyncSessionLocal,
    )


@router.post("/twilio/dial-status")
async def handle_dial_status(
    CallSid: Optional[str] = Form(None),
    DialCallSid: Optional[str] = Form(None),
    DialCallStatus: Optional[str] = Form(None),
    DialCallDuration: Optional[str] = Form(None),
    _valid: bool = Depends(validate_twilio_request),
):
    return await handle_twilio_dial_status(
        CallSid=CallSid,
        DialCallSid=DialCallSid,
        DialCallStatus=DialCallStatus,
        DialCallDuration=DialCallDuration,
        session_factory=AsyncSessionLocal,
    )


@router.post("/twilio/sip-status")
async def handle_sip_status(
    parent_call_sid: Optional[str] = Query(None),
    CallSid: Optional[str] = Form(None),
    CallStatus: Optional[str] = Form(None),
    _valid: bool = Depends(validate_twilio_request),
):
    return await handle_twilio_sip_status(
        parent_call_sid=parent_call_sid,
        CallSid=CallSid,
        CallStatus=CallStatus,
        session_factory=AsyncSessionLocal,
    )


@router.post("/twilio/status")
async def handle_call_status(
    CallSid: Optional[str] = Form(None),
    CallStatus: Optional[str] = Form(None),
    CallDuration: Optional[str] = Form(None),
    _valid: bool = Depends(validate_twilio_request),
):
    return await handle_twilio_status(
        CallSid=CallSid,
        CallStatus=CallStatus,
        CallDuration=CallDuration,
        session_factory=AsyncSessionLocal,
    )
