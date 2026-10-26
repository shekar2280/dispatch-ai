from typing import Optional, List, Dict
from uuid import UUID
import uuid
from datetime import time
from fastapi import HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.user import User
from app.models.admin_setting import AdminSetting
from app.models.doctor_schedule import DoctorSchedule
from app.services.voice.call_session import invalidate_specialties_cache
from app.services.infra.websocket_manager import ws_manager

RECOMMENDED_SPECIALTY_TAGS: Dict[str, List[str]] = {
    "Dermatology": ["dermatology", "skin rashes", "skin crashes", "acne", "eczema", "itching", "skin"],
    "Cardiology": ["cardiology", "chest pain", "heart", "palpitations", "blood pressure"],
    "General Medicine": ["general medicine", "fever", "cough", "flu", "checkup", "consultation", "routine"],
    "Orthopedics": ["orthopedics", "joint pain", "bone", "fracture", "back pain"],
    "Pediatrics": ["pediatrics", "child", "baby", "pediatric"],
    "Neurology": ["neurology", "headache", "migraine", "dizziness"],
}


class MemberCreateRequest(BaseModel):
    org_id: Optional[UUID] = None
    full_name: str
    email: EmailStr
    role: str
    specialization: Optional[str] = None
    specialty_tags: Optional[List[str]] = []
    vehicle_number: Optional[str] = None
    station_number: Optional[str] = None


class MemberStatusUpdateRequest(BaseModel):
    presence_status: str


async def create_team_member_service(
    db: AsyncSession,
    req: MemberCreateRequest,
    current_org_id: UUID,
):
    from app.services.clinic.dashboard_service import add_clinic_staff_service
    if req.role.lower().strip() != "receptionist":
        raise HTTPException(status_code=400, detail="This is a single-doctor clinic. Only receptionists can be invited.")
    return await add_clinic_staff_service(db, current_org_id, str(req.email), req.full_name, "receptionist")


async def get_team_members_service(
    db: AsyncSession,
    target_org_id: UUID,
):
    query = select(User).where(User.org_id == target_org_id)
    res = await db.execute(query)
    users = list(res.scalars().all())

    members = []
    for u in users:
        role_str = str(getattr(u.role, "value", u.role)).lower()
        ext_data = {}

        if role_str == "doctor":
            ext_data = {
                "specialization": u.specialization,
                "specialty_tags": getattr(u, "specialty_tags", None) or [],
            }

        members.append({
            "id": str(u.id),
            "full_name": u.full_name,
            "email": u.email,
            "role": role_str,
            "presence_status": str(getattr(u.presence_status, "value", u.presence_status)),
            "extension": ext_data,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        })

    return {
        "status": "success",
        "count": len(members),
        "members": members,
    }


async def update_member_status_service(
    db: AsyncSession,
    user_id: UUID,
    status_clean: str,
    current_org_id: UUID,
):
    valid_statuses = [
        "available",
        "busy",
        "offline",
        "in_surgery",
        "on_leave",
        "unavailable",
        "duty_rounds",
        "emergency",
        "en_route",
        "on_scene",
        "transporting",
    ]
    if status_clean not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")

    user_res = await db.execute(select(User).where(User.id == user_id))
    user = user_res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Team member not found.")
    if user.org_id != current_org_id:
        raise HTTPException(status_code=403, detail="Forbidden: Cross-tenant access denied")

    user.presence_status = status_clean
    await db.commit()
    await db.refresh(user)

    if user.org_id:
        role_name = str(getattr(user.role, "value", user.role)).lower()
        await ws_manager.broadcast_to_org(
            str(user.org_id),
            {
                "event": "MEMBER_PRESENCE_UPDATED",
                "user_id": str(user.id),
                "member_name": user.full_name,
                "doctor_name": user.full_name,
                "role": role_name,
                "presence_status": status_clean,
            },
        )
        await ws_manager.broadcast_to_org(
            str(user.org_id),
            {
                "event": "DOCTOR_PRESENCE_UPDATED",
                "user_id": str(user.id),
                "doctor_name": user.full_name,
                "role": role_name,
                "presence_status": status_clean,
            },
        )

    return {
        "status": "success",
        "user_id": str(user.id),
        "presence_status": str(getattr(user.presence_status, "value", user.presence_status)),
        "message": f"Updated status to {status_clean} for {user.full_name}",
    }


async def deactivate_team_member_service(
    db: AsyncSession,
    user_id: UUID,
    current_org_id: UUID,
):
    from app.services.clinic.dashboard_service import remove_clinic_staff_service
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Team member not found.")
    return await remove_clinic_staff_service(db, current_org_id, user.email)
