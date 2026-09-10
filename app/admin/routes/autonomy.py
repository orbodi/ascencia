from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.deps import require_admin_user, require_admin_write
from app.api.deps import get_db
from app.domain.models import AdminUser
from app.services.autonomous_workflow import AutonomousWorkflowService


router = APIRouter(prefix="/admin/autonomy", tags=["admin-autonomy"])


@router.get("")
async def autonomy_status(
    week_start: date | None = Query(default=None),
    _user: AdminUser = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    return await AutonomousWorkflowService(session).status(week_start)


@router.post("/run")
async def run_autonomous_cycle(
    week_start: date | None = Query(default=None),
    user: AdminUser = Depends(require_admin_write),
    session: AsyncSession = Depends(get_db),
) -> dict:
    try:
        return await AutonomousWorkflowService(session).run_once(
            week_start, initiated_by=f"admin:{user.username}"
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
