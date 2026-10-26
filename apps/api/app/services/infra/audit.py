from typing import Any, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.audit_log import SystemAuditLog

SENSITIVE_KEYS = {"address", "chief_complaint", "diagnosis", "dob", "email", "medical_history", "notes", "phone", "phone_number", "prescriptions", "recent_diagnosis"}

def audit_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): "[redacted]" if str(k).lower() in SENSITIVE_KEYS else audit_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return f"[{len(value)} item(s)]"
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)[:120]

async def write_audit_event(db: AsyncSession, *, org_id: UUID, action_type: str, target_id: Optional[UUID] = None, target_name: str = "", actor_id: Optional[UUID] = None, actor_email: str = "system@dispatch.local", old_state: Optional[dict] = None, new_state: Optional[dict] = None, metadata: Optional[dict] = None) -> None:
    db.add(SystemAuditLog(org_id=org_id, actor_id=actor_id, actor_email=(actor_email or "system@dispatch.local")[:255], action_type=action_type, target_id=target_id, target_name=target_name, old_state=audit_safe(old_state or {}), new_state=audit_safe(new_state or {}), log_metadata=audit_safe(metadata or {})))
    await db.flush()
