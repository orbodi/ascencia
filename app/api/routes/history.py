from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_api_token
from app.services.history_service import HistoryService

router = APIRouter(prefix="/history", dependencies=[Depends(require_api_token)])


@router.get("/teacher-actions")
async def teacher_actions_history(
    kind: str = Query(
        default="all",
        pattern="^(all|confirmations|reschedules|reminders)$",
    ),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Historique admin : confirmations de présence et reports/annulations."""
    return await HistoryService(session).teacher_actions(kind=kind, limit=limit)
