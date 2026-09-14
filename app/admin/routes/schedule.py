from datetime import date, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.admin.deps import require_admin_user, require_admin_write
from app.admin.schemas_crud import (
    ScheduleEntryIn,
    ScheduleEntryOut,
    TimeSlotIn,
    TimeSlotOut,
)
from app.api.deps import get_db
from app.domain.models import (
    AdminUser,
    Course,
    ScheduleEntry,
    ScheduleEntryStatus,
    TimeSlot,
)
from app.exporters import PdfExporter
from app.services.planning_service import PlanningService

router = APIRouter(tags=["admin-schedule"])


def _parse_time(value: str) -> time:
    parts = value.split(":")
    return time(int(parts[0]), int(parts[1]))


@router.get("/admin/timeslots", response_model=list[TimeSlotOut])
async def list_timeslots(
    _user: AdminUser = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db),
) -> list[dict]:
    rows = (
        await session.execute(select(TimeSlot).order_by(TimeSlot.day_of_week, TimeSlot.start_time))
    ).scalars().all()
    return [
        {
            "id": s.id,
            "day_of_week": s.day_of_week,
            "start_time": s.start_time.strftime("%H:%M"),
            "end_time": s.end_time.strftime("%H:%M"),
            "label": s.label,
        }
        for s in rows
    ]


@router.post("/admin/timeslots", response_model=TimeSlotOut, status_code=201)
async def create_timeslot(
    body: TimeSlotIn,
    _user: AdminUser = Depends(require_admin_write),
    session: AsyncSession = Depends(get_db),
) -> dict:
    slot = TimeSlot(
        day_of_week=body.day_of_week,
        start_time=_parse_time(body.start_time),
        end_time=_parse_time(body.end_time),
        label=body.label,
    )
    session.add(slot)
    await session.commit()
    await session.refresh(slot)
    return {
        "id": slot.id,
        "day_of_week": slot.day_of_week,
        "start_time": slot.start_time.strftime("%H:%M"),
        "end_time": slot.end_time.strftime("%H:%M"),
        "label": slot.label,
    }


@router.get("/admin/schedule", response_model=list[ScheduleEntryOut])
async def list_schedule(
    week_start: date | None = Query(default=None),
    _user: AdminUser = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db),
) -> list[dict]:
    stmt = (
        select(ScheduleEntry)
        .options(
            selectinload(ScheduleEntry.course).selectinload(Course.teacher),
            selectinload(ScheduleEntry.course).selectinload(Course.group),
            selectinload(ScheduleEntry.room),
            selectinload(ScheduleEntry.timeslot),
        )
        .order_by(ScheduleEntry.entry_date, ScheduleEntry.timeslot_id)
    )
    if week_start is not None:
        monday = week_start - timedelta(days=week_start.weekday())
        sunday = monday + timedelta(days=6)
        stmt = stmt.where(
            ScheduleEntry.entry_date >= monday,
            ScheduleEntry.entry_date <= sunday,
        )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": e.id,
            "course_id": e.course_id,
            "room_id": e.room_id,
            "timeslot_id": e.timeslot_id,
            "entry_date": e.entry_date,
            "status": e.status,
            "course_title": e.course.title if e.course else None,
            "teacher_name": e.course.teacher.name if e.course and e.course.teacher else None,
            "group_name": e.course.group.name if e.course and e.course.group else None,
            "room_name": e.room.name if e.room else None,
            "timeslot_label": e.timeslot.label if e.timeslot else None,
        }
        for e in rows
    ]


@router.post("/admin/schedule", response_model=ScheduleEntryOut, status_code=201)
async def create_schedule_entry(
    body: ScheduleEntryIn,
    _user: AdminUser = Depends(require_admin_write),
    session: AsyncSession = Depends(get_db),
) -> dict:
    try:
        conflicts = await PlanningService(session).validate_schedule_entry(
            course_id=body.course_id,
            room_id=body.room_id,
            timeslot_id=body.timeslot_id,
            entry_date=body.entry_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if conflicts:
        raise HTTPException(status_code=409, detail={"conflicts": conflicts})
    entry = ScheduleEntry(**body.model_dump())
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return {
        "id": entry.id,
        **body.model_dump(),
    }


@router.patch("/admin/schedule/{entry_id}", response_model=ScheduleEntryOut)
async def update_schedule_entry(
    entry_id: int,
    body: ScheduleEntryIn,
    _user: AdminUser = Depends(require_admin_write),
    session: AsyncSession = Depends(get_db),
) -> dict:
    entry = await session.get(ScheduleEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Séance introuvable")
    try:
        conflicts = await PlanningService(session).validate_schedule_entry(
            course_id=body.course_id,
            room_id=body.room_id,
            timeslot_id=body.timeslot_id,
            entry_date=body.entry_date,
            ignore_entry_id=entry_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if conflicts:
        raise HTTPException(status_code=409, detail={"conflicts": conflicts})
    for key, value in body.model_dump().items():
        setattr(entry, key, value)
    await session.commit()
    await session.refresh(entry)
    return {"id": entry.id, **body.model_dump()}


@router.post("/admin/schedule/{entry_id}/cancel", response_model=ScheduleEntryOut)
async def cancel_schedule_entry(
    entry_id: int,
    _user: AdminUser = Depends(require_admin_write),
    session: AsyncSession = Depends(get_db),
) -> dict:
    entry = await session.get(ScheduleEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Séance introuvable")
    entry.status = ScheduleEntryStatus.cancelled
    await session.commit()
    return {
        "id": entry.id,
        "course_id": entry.course_id,
        "room_id": entry.room_id,
        "timeslot_id": entry.timeslot_id,
        "entry_date": entry.entry_date,
        "status": entry.status,
    }


@router.get("/admin/schedule/export/pdf")
async def export_week_pdf(
    week_start: date | None = Query(default=None),
    preview: bool = Query(default=False),
    _user: AdminUser = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db),
) -> FileResponse:
    try:
        result = await PdfExporter(session).generate_week_schedule_pdf(
            week_start=week_start,
            preview=preview,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur génération PDF: {exc}",
        ) from exc
    return FileResponse(
        path=result["path"],
        media_type=result.get("media_type", "application/pdf"),
        filename=result["filename"],
        content_disposition_type="inline" if preview else "attachment",
    )


@router.get("/admin/schedule/export/pdf/teacher/{teacher_id}")
async def export_teacher_pdf_admin(
    teacher_id: int,
    week_start: date | None = Query(default=None),
    _user: AdminUser = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db),
) -> FileResponse:
    try:
        result = await PdfExporter(session).generate_teacher_schedule_pdf(
            teacher_id, week_start=week_start
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
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


@router.get("/admin/schedule/export/pdf/group/{group_id}")
async def export_group_pdf_admin(
    group_id: int,
    week_start: date | None = Query(default=None),
    _user: AdminUser = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db),
) -> FileResponse:
    try:
        result = await PdfExporter(session).generate_group_schedule_pdf(
            group_id, week_start=week_start
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
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
