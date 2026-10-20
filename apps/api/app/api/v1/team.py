from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_tenant_org, require_clinic_administrator
from app.services.clinic.team_service import (
    RECOMMENDED_SPECIALTY_TAGS,
    MemberCreateRequest,
    MemberStatusUpdateRequest,
    create_team_member_service,
    get_team_members_service,
    update_member_status_service,
    deactivate_team_member_service,
)

router = APIRouter()


@router.get("/recommendations")
async def get_specialty_recommendations():
    return {
        "status": "success",
        "recommendations": RECOMMENDED_SPECIALTY_TAGS,
    }


@router.post("/members")
async def create_team_member(
    req: MemberCreateRequest,
    current_org_id: UUID = Depends(require_clinic_administrator),
    db: AsyncSession = Depends(get_db),
):
    return await create_team_member_service(db, req, current_org_id)


@router.get("/members")
@router.get("/members/{org_id}")
async def list_team_members(
    org_id: Optional[UUID] = None,
    current_org_id: UUID = Depends(get_current_tenant_org),
    db: AsyncSession = Depends(get_db),
):
    from fastapi import HTTPException
    target_org_id = org_id or current_org_id
    if current_org_id != target_org_id:
        raise HTTPException(status_code=403, detail="Forbidden: Cross-tenant access denied")
    return await get_team_members_service(db, target_org_id)


@router.patch("/members/{user_id}/status")
async def update_member_status(
    user_id: UUID,
    req: MemberStatusUpdateRequest,
    current_org_id: UUID = Depends(require_clinic_administrator),
    db: AsyncSession = Depends(get_db),
):
    return await update_member_status_service(
        db, user_id, req.presence_status.lower().strip(), current_org_id
    )


@router.post("/members/{user_id}/deactivate")
@router.delete("/members/{user_id}")
async def deactivate_member(
    user_id: UUID,
    current_org_id: UUID = Depends(require_clinic_administrator),
    db: AsyncSession = Depends(get_db),
):
    return await deactivate_team_member_service(db, user_id, current_org_id)
