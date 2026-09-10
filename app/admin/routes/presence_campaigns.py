from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.deps import require_admin_user, require_admin_write
from app.api.deps import get_db
from app.domain.models import AdminUser
from app.services.presence_service import PresenceCampaignService

router = APIRouter(prefix="/admin/presence-campaigns", tags=["admin-presence"])


class CampaignCreate(BaseModel):
    publication_id: int = Field(gt=0)
    channels: list[str] = Field(default_factory=lambda: ["email", "whatsapp"])


@router.get("")
async def campaign_for_publication(
    publication_id: int = Query(gt=0),
    _user: AdminUser = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    campaign = await PresenceCampaignService(session).campaign_for_publication(
        publication_id
    )
    return {"campaign": campaign}


@router.post("", status_code=201)
async def create_campaign(
    body: CampaignCreate,
    user: AdminUser = Depends(require_admin_write),
    session: AsyncSession = Depends(get_db),
) -> dict:
    try:
        return await PresenceCampaignService(session).create_campaign(
            body.publication_id,
            created_by=user.username,
            channels=body.channels,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{campaign_id}/send")
async def send_campaign(
    campaign_id: int,
    _user: AdminUser = Depends(require_admin_write),
    session: AsyncSession = Depends(get_db),
) -> dict:
    try:
        return await PresenceCampaignService(session).send_campaign(campaign_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
