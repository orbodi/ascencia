from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_api_token
from app.exporters import PdfExporter

router = APIRouter(prefix="/schedule/export", dependencies=[Depends(require_api_token)])


@router.get("/pdf/teacher/{teacher_id}")
async def export_teacher_pdf(
    teacher_id: int,
    week_start: date | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> FileResponse:
    try:
        result = await PdfExporter(session).generate_teacher_schedule_pdf(
            teacher_id, week_start=week_start
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur génération PDF: {exc}",
        ) from exc

    return FileResponse(
        path=result["path"],
        media_type="application/pdf",
        filename=result["filename"],
    )


@router.get("/pdf/group/{group_id}")
async def export_group_pdf(
    group_id: int,
    week_start: date | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> FileResponse:
    try:
        result = await PdfExporter(session).generate_group_schedule_pdf(
            group_id, week_start=week_start
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur génération PDF: {exc}",
        ) from exc

    return FileResponse(
        path=result["path"],
        media_type="application/pdf",
        filename=result["filename"],
    )
