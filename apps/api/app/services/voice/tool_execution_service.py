import logging
from typing import Dict, Any, List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.voice.handlers.tool_registry import (
    dispatch_tool_execution,
    SUPPORTED_TOOLS,
)

logger = logging.getLogger(__name__)

TOOL_REGISTRY = SUPPORTED_TOOLS


def generate_dynamic_voice_tools(
    admin_required_fields: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    return []


async def execute_tool_call(
    tool_name: str,
    arguments: Dict[str, Any],
    db: AsyncSession,
    org_id: UUID,
    clean_phone: Optional[str] = None,
    call_session_id: Optional[UUID] = None,
) -> Dict[str, Any]:
    return await dispatch_tool_execution(
        tool_name=tool_name,
        arguments=arguments,
        db=db,
        org_id=org_id,
        clean_phone=clean_phone,
        call_session_id=call_session_id,
    )
