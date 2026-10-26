import uuid
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.call_session import CallLog
from app.models.voice_workflow_checkpoint import VoiceWorkflowCheckpoint
from app.services.voice.workflow.state import VoiceWorkflowState


class OptimisticLockError(Exception):
    pass


async def save_checkpoint(
    db: AsyncSession,
    org_id: UUID,
    call_id: UUID,
    state: VoiceWorkflowState,
    status: str = "active",
    ttl_seconds: int = 1800,
    resumed_from_call_id: UUID | None = None,
    expected_state_version: int | None = None,
) -> VoiceWorkflowCheckpoint:
    now = datetime.now(UTC)
    expires = now + timedelta(seconds=ttl_seconds)
    safe_data = state.to_safe_dict()

    stmt = select(VoiceWorkflowCheckpoint).where(
        VoiceWorkflowCheckpoint.org_id == org_id,
        VoiceWorkflowCheckpoint.call_id == call_id,
    ).with_for_update()
    existing = await db.scalar(stmt)

    if not existing:
        checkpoint = VoiceWorkflowCheckpoint(
            id=uuid.uuid4(),
            org_id=org_id,
            call_id=call_id,
            resumed_from_call_id=resumed_from_call_id,
            workflow_version=state.workflow_version,
            state_version=state.state_version,
            status=status,
            stage=state.stage.value,
            safe_state=safe_data,
            last_completed_event_id=state.last_completed_event_id,
            expires_at=expires,
            created_at=now,
            updated_at=now,
        )
        db.add(checkpoint)
        await db.commit()
        await db.refresh(checkpoint)
        return checkpoint

    target_expected = expected_state_version if expected_state_version is not None else existing.state_version
    if existing.state_version != target_expected:
        raise OptimisticLockError(
            f"Stale checkpoint state version {target_expected}; database is at {existing.state_version}"
        )

    new_version = max(state.state_version, existing.state_version + 1)
    update_stmt = (
        update(VoiceWorkflowCheckpoint)
        .where(
            VoiceWorkflowCheckpoint.org_id == org_id,
            VoiceWorkflowCheckpoint.call_id == call_id,
            VoiceWorkflowCheckpoint.state_version == target_expected,
        )
        .values(
            state_version=new_version,
            stage=state.stage.value,
            status=status,
            safe_state=safe_data,
            last_completed_event_id=state.last_completed_event_id,
            expires_at=expires,
            updated_at=now,
        )
    )
    result = await db.execute(update_stmt)
    if result.rowcount == 0:
        raise OptimisticLockError(
            f"Optimistic lock conflict updating checkpoint for call {call_id} at version {target_expected}"
        )

    await db.commit()
    refreshed = await db.scalar(
        select(VoiceWorkflowCheckpoint).where(
            VoiceWorkflowCheckpoint.org_id == org_id,
            VoiceWorkflowCheckpoint.call_id == call_id,
        )
    )
    return refreshed


async def load_checkpoint(
    db: AsyncSession,
    org_id: UUID,
    call_id: UUID,
) -> VoiceWorkflowCheckpoint | None:
    stmt = select(VoiceWorkflowCheckpoint).where(
        VoiceWorkflowCheckpoint.org_id == org_id,
        VoiceWorkflowCheckpoint.call_id == call_id,
    )
    return await db.scalar(stmt)


async def find_resumable_checkpoint(
    db: AsyncSession,
    org_id: UUID,
    caller_phone: str,
    max_age_seconds: int = 900,
) -> tuple[VoiceWorkflowCheckpoint, CallLog] | None:
    now = datetime.now(UTC)
    cutoff = now - timedelta(seconds=max_age_seconds)

    stmt = (
        select(VoiceWorkflowCheckpoint, CallLog)
        .join(CallLog, (CallLog.id == VoiceWorkflowCheckpoint.call_id) & (CallLog.org_id == VoiceWorkflowCheckpoint.org_id))
        .where(
            VoiceWorkflowCheckpoint.org_id == org_id,
            CallLog.caller_phone == caller_phone,
            VoiceWorkflowCheckpoint.status == "active",
            VoiceWorkflowCheckpoint.expires_at > now,
            VoiceWorkflowCheckpoint.created_at >= cutoff,
        )
        .order_by(VoiceWorkflowCheckpoint.created_at.desc())
        .limit(1)
    )
    row = (await db.execute(stmt)).first()
    if not row:
        return None
    return row[0], row[1]


async def mark_checkpoint_resumed(
    db: AsyncSession,
    checkpoint_id: UUID,
    new_call_id: UUID,
) -> bool:
    now = datetime.now(UTC)
    stmt = (
        update(VoiceWorkflowCheckpoint)
        .where(VoiceWorkflowCheckpoint.id == checkpoint_id)
        .values(
            status="resumed",
            resumed_at=now,
            updated_at=now,
        )
    )
    res = await db.execute(stmt)
    await db.commit()
    return res.rowcount > 0


async def mark_checkpoint_completed(
    db: AsyncSession,
    org_id: UUID,
    call_id: UUID,
) -> bool:
    now = datetime.now(UTC)
    stmt = (
        update(VoiceWorkflowCheckpoint)
        .where(
            VoiceWorkflowCheckpoint.org_id == org_id,
            VoiceWorkflowCheckpoint.call_id == call_id,
        )
        .values(
            status="completed",
            updated_at=now,
        )
    )
    res = await db.execute(stmt)
    await db.commit()
    return res.rowcount > 0


async def purge_expired_checkpoints(
    db: AsyncSession,
    batch_size: int = 100,
) -> int:
    now = datetime.now(UTC)
    subquery = (
        select(VoiceWorkflowCheckpoint.id)
        .where(VoiceWorkflowCheckpoint.expires_at < now)
        .limit(batch_size)
    )
    stmt = delete(VoiceWorkflowCheckpoint).where(VoiceWorkflowCheckpoint.id.in_(subquery))
    res = await db.execute(stmt)
    await db.commit()
    return res.rowcount
