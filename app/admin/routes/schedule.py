from datetime import date, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
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
