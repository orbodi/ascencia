from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.deps import require_admin_user
from app.api.deps import get_db
from app.domain.models import AdminUser
from app.services.history_service import HistoryService

router = APIRouter(prefix="/admin/history", tags=["admin-history"])


@router.get("/teacher-actions")
async def teacher_actions_history(
    kind: str = Query(
        default="all",
        pattern="^(all|confirmations|reschedules|reminders)$",
    ),
    limit: int = Query(default=50, ge=1, le=200),
    _user: AdminUser = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    return await HistoryService(session).teacher_actions(kind=kind, limit=limit)
