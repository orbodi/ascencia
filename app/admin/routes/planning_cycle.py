"""API cycle planning (dates Dashboard + exécution)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.deps import require_admin_user, require_admin_write
from app.api.deps import get_db
from app.domain.models import AdminUser
from app.services.planning_cycle import PlanningCycleService

router = APIRouter(prefix="/admin/planning-cycle", tags=["admin-planning-cycle"])


class PlanningCycleDatesIn(BaseModel):
    collection_start_date: str | None = Field(
        default=None, description="AAAA-MM-JJ début collecte WhatsApp"
    )
    publication_date: str | None = Field(
        default=None, description="AAAA-MM-JJ envoi planning aux admins"
    )
    target_week_start: str | None = Field(
        default=None, description="Lundi semaine cible (optionnel)"
    )


@router.get("")
async def planning_cycle_status(
    _user: AdminUser = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    return await PlanningCycleService(session).status()


@router.put("/dates")
async def update_planning_cycle_dates(
    body: PlanningCycleDatesIn,
    user: AdminUser = Depends(require_admin_write),
    session: AsyncSession = Depends(get_db),
) -> dict:
    try:
        return await PlanningCycleService(session).update_dates(
            collection_start_date=body.collection_start_date,
            publication_date=body.publication_date,
            target_week_start=body.target_week_start,
            updated_by=user.username,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.post("/run")
async def run_planning_cycle(
    user: AdminUser = Depends(require_admin_write),
    session: AsyncSession = Depends(get_db),
) -> dict:
    try:
        return await PlanningCycleService(session).run_once(
            initiated_by=f"admin:{user.username}"
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
