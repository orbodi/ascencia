from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.deps import require_admin_user, require_admin_write
from app.admin.schemas_crud import (
    PublicationDraftIn,
    PublicationOut,
    PublicationPublishIn,
)
from app.api.deps import get_db
from app.domain.models import AdminUser, SchedulePublication
from app.exporters.excel import EXPORTS_DIR
from app.services.generation_service import ScheduleGenerationService
from app.services.distribution_service import PublicationDistributionService

router = APIRouter(prefix="/admin/publications", tags=["admin-publications"])


def _serialize(item: SchedulePublication) -> dict:
    return {
        "id": item.id,
        "version_number": item.version_number,
        "week_start": item.week_start,
        "week_end": item.week_end,
        "status": item.status,
        "snapshot_json": item.snapshot_json,
        "generation_report": item.generation_report,
        "created_by": item.created_by,
        "published_by": item.published_by,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "published_at": item.published_at.isoformat() if item.published_at else None,
        "xlsx_path": item.xlsx_path,
    }


@router.get("", response_model=list[PublicationOut])
async def list_publications(
    _user: AdminUser = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db),
) -> list[dict]:
    rows = await ScheduleGenerationService(session).list_publications()
    return [_serialize(row) for row in rows]


@router.post("/generate", response_model=PublicationOut, status_code=201)
async def generate_publication_draft(
    body: PublicationDraftIn,
    user: AdminUser = Depends(require_admin_write),
    session: AsyncSession = Depends(get_db),
) -> dict:
    item = await ScheduleGenerationService(session).generate_draft(
        body.week_start, created_by=user.username
    )
    return _serialize(item)


@router.post("/{publication_id}/publish")
async def publish_schedule(
    publication_id: int,
    body: PublicationPublishIn | None = None,
    user: AdminUser = Depends(require_admin_write),
    session: AsyncSession = Depends(get_db),
) -> dict:
    try:
        item = await ScheduleGenerationService(session).publish(
            publication_id,
            published_by=user.username,
            force_presence_override=(body or PublicationPublishIn()).force_presence_override,
        )
        distribution = await PublicationDistributionService(session).distribute(
            publication_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"publication": _serialize(item), "distribution": distribution}


@router.post("/{publication_id}/redistribute")
async def redistribute_schedule(
    publication_id: int,
    _user: AdminUser = Depends(require_admin_write),
    session: AsyncSession = Depends(get_db),
) -> dict:
    try:
        return await PublicationDistributionService(session).distribute(publication_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{publication_id}/deliveries")
async def publication_deliveries(
    publication_id: int,
    _user: AdminUser = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    return {
        "deliveries": await PublicationDistributionService(session).history(
            publication_id
        )
    }


@router.get("/{publication_id}/xlsx")
async def download_publication_xlsx(
    publication_id: int,
    _user: AdminUser = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db),
) -> FileResponse:
    publication = await session.get(SchedulePublication, publication_id)
    if publication is None or not publication.xlsx_path:
        raise HTTPException(status_code=404, detail="Fichier Excel non disponible")
    path = Path(publication.xlsx_path).resolve()
    if EXPORTS_DIR.resolve() not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="Fichier Excel introuvable")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=path.name,
    )
