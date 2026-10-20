"""
Voice Services Module
Exports tool_execution_service for voice AI execution.
"""

from app.services.voice.tool_execution_service import (
    execute_tool_call,
    generate_dynamic_voice_tools,
)

__all__ = [
    "execute_tool_call",
    "generate_dynamic_voice_tools",
]
