import hmac
from typing import Optional
from uuid import UUID
from fastapi import Header, Query, HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from supabase import AuthApiError, create_client
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.models.clinic_membership import ClinicMembership
from app.services.infra.redis_cache import distributed_redis


def get_supabase_admin_client():
    url = settings.SUPABASE_URL or settings.NEXT_PUBLIC_SUPABASE_URL
    key = settings.SUPABASE_SERVICE_ROLE_KEY
    if not url or not key:
        return None
    return create_client(url, key)


async def get_verified_auth_identity(
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> dict:
    scheme, separator, token = (authorization or "").partition(" ")
    token = token.strip()
    if separator != " " or scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    client = get_supabase_admin_client()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable.",
        )

    try:
        auth_res = await run_in_threadpool(client.auth.get_user, token)
    except AuthApiError as error:
        if error.status not in (400, 401, 403):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service unavailable.",
            ) from error
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication session.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable.",
        ) from error

    auth_user = getattr(auth_res, "user", None)
    if (
        not auth_user
        or not getattr(auth_user, "id", None)
        or not getattr(auth_user, "email", None)
        or not getattr(auth_user, "email_confirmed_at", None)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="An authenticated account with an email address is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        auth_user_id = UUID(str(auth_user.id))
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authenticated account.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {
        "id": auth_user_id,
        "email": auth_user.email.strip().lower(),
        "full_name": (getattr(auth_user, "user_metadata", None) or {}).get("full_name"),
    }


async def resolve_org_tenant_type(org_id: UUID) -> str:
    return "CLINIC"


async def invalidate_org_tenant_cache(org_id: UUID) -> None:
    redis_client = await distributed_redis.get_client()
    if redis_client:
        try:
            await redis_client.delete(f"org_tenant:{str(org_id)}")
        except Exception:
            pass


async def get_current_user(
    identity: dict = Depends(get_verified_auth_identity),
    db: AsyncSession = Depends(get_db),
) -> User:
    user_record: Optional[User] = await db.get(User, identity["id"])

    if not user_record:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registered user record not found in practice directory.",
        )

    if not user_record.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account has been deactivated.",
        )

    return user_record


async def get_current_tenant_org(
    x_org_id: Optional[str] = Header(None, alias="X-Org-Id"),
    tenant_org_query: Optional[UUID] = Query(None, alias="org_id"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UUID:
    requested_org: Optional[UUID] = None
    if x_org_id:
        try:
            requested_org = UUID(x_org_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid X-Org-Id header format.",
            )
    elif tenant_org_query:
        requested_org = tenant_org_query

    user_id = getattr(current_user, "id", None)

    if requested_org:
        if user_id:
            membership = await db.scalar(
                select(ClinicMembership).where(
                    ClinicMembership.org_id == requested_org,
                    ClinicMembership.user_id == user_id,
                    ClinicMembership.status == "active",
                )
            )
            if membership:
                return requested_org
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: you do not have permission to access resources in another clinic tenant.",
        )

    if user_id:
        active_membership = await db.scalar(
            select(ClinicMembership)
            .where(
                ClinicMembership.user_id == user_id,
                ClinicMembership.status == "active",
            )
            .order_by(ClinicMembership.created_at.asc())
        )
        if active_membership:
            return active_membership.org_id

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="User has no active clinic memberships.",
    )


def require_tenant(expected_tenant: str):
    async def tenant_dependency(
        resolved_org_id: UUID = Depends(get_current_tenant_org),
    ) -> UUID:
        return resolved_org_id

    return tenant_dependency


async def require_admin_key(
    x_admin_key: Optional[str] = Header(None, alias="X-Admin-Key"),
) -> bool:
    expected_key = settings.ADMIN_SECRET_KEY
    if not expected_key or not x_admin_key or not hmac.compare_digest(x_admin_key, expected_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrative access key missing or invalid.",
        )
    return True


async def is_clinic_administrator(db: AsyncSession, org_id: UUID, user_id: UUID) -> bool:
    membership = await db.scalar(select(ClinicMembership).where(
        ClinicMembership.org_id == org_id,
        ClinicMembership.user_id == user_id,
        ClinicMembership.status == "active",
        ClinicMembership.role == "admin",
    ))
    return membership is not None


async def require_clinic_administrator(
    org_id: UUID = Depends(get_current_tenant_org),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UUID:
    if not await is_clinic_administrator(db, org_id, current_user.id):
        raise HTTPException(status_code=403, detail="Only the clinic owner can manage clinic access.")
    return org_id
