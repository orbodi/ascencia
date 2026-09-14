"""API admin — collecte disponibilités enseignants."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.deps import require_admin_user, require_admin_write
from app.api.deps import get_db
from app.domain.models import AdminUser
from app.services.availability_outreach import AvailabilityOutreachService

router = APIRouter(prefix="/admin/outreach", tags=["admin-outreach"])


class AvailabilityFormSendIn(BaseModel):
    channel: str = Field(default="both", pattern="^(email|whatsapp|both)$")
    teacher_id: int | None = None
    teacher_ids: list[int] | None = None
    approved_by: str | None = None


@router.get("/availability-form/preview")
async def preview_availability_form(
    channel: str = "both",
    teacher_id: int | None = None,
    _user: AdminUser = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    if channel not in {"email", "whatsapp", "both"}:
        raise HTTPException(status_code=400, detail="Canal invalide")
    return await AvailabilityOutreachService(session).preview(
        teacher_id=teacher_id,
        channel=channel,  # type: ignore[arg-type]
    )


@router.post("/availability-form/send")
async def send_availability_form(
    body: AvailabilityFormSendIn,
    user: AdminUser = Depends(require_admin_write),
    session: AsyncSession = Depends(get_db),
) -> dict:
    try:
        return await AvailabilityOutreachService(session).send(
            channel=body.channel,  # type: ignore[arg-type]
            approved_by=(body.approved_by or user.username).strip(),
            teacher_id=body.teacher_id,
            teacher_ids=body.teacher_ids,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
