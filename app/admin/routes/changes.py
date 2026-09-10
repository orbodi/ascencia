from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.deps import require_admin_user, require_admin_write
from app.admin.schemas_crud import ChangeOut
from app.api.deps import get_db
from app.domain.models import AdminUser, ScheduleChange, ScheduleChangeStatus
from app.services.planning_service import PlanningService

router = APIRouter(prefix="/admin/changes", tags=["admin-changes"])


@router.get("", response_model=list[ChangeOut])
async def list_changes(
    status_filter: ScheduleChangeStatus | None = None,
    _user: AdminUser = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db),
) -> list[dict]:
    stmt = select(ScheduleChange).order_by(ScheduleChange.id.desc())
    if status_filter is not None:
        stmt = stmt.where(ScheduleChange.status == status_filter)
    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": c.id,
            "entry_id": c.entry_id,
            "before_json": c.before_json,
            "after_json": c.after_json,
            "status": c.status,
            "proposed_by": c.proposed_by,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in rows
    ]


@router.post("/{change_id}/approve")
async def approve_change(
    change_id: int,
    user: AdminUser = Depends(require_admin_write),
    session: AsyncSession = Depends(get_db),
) -> dict:
    try:
        return await PlanningService(session).approve_schedule_change(
            change_id, approved_by=user.username
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{change_id}/apply")
async def apply_change(
    change_id: int,
    _user: AdminUser = Depends(require_admin_write),
    session: AsyncSession = Depends(get_db),
) -> dict:
    try:
        return await PlanningService(session).apply_schedule_change(change_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{change_id}/reject")
async def reject_change(
    change_id: int,
    _user: AdminUser = Depends(require_admin_write),
    session: AsyncSession = Depends(get_db),
) -> dict:
    change = await session.get(ScheduleChange, change_id)
    if change is None:
        raise HTTPException(status_code=404, detail="Changement introuvable")
    if change.status != ScheduleChangeStatus.proposed:
        raise HTTPException(
            status_code=400, detail="Seuls les proposed peuvent être rejetés"
        )
    change.status = ScheduleChangeStatus.rejected
    change.decided_at = datetime.now(timezone.utc)
    await session.commit()
    return {"ok": True, "change_id": change_id, "status": "rejected"}
