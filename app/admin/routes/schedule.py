from datetime import date, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
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
    ScheduleChange,
    ScheduleEntry,
    ScheduleEntryStatus,
    TimeSlot,
)
from app.exporters import PdfExporter
from app.services.display import strip_level_code
from app.services.planning_service import PlanningService

router = APIRouter(tags=["admin-schedule"])


def _parse_time(value: str) -> time:
    parts = value.split(":")
    return time(int(parts[0]), int(parts[1]))


def _serialize_timeslot(slot: TimeSlot) -> dict:
    return {
        "id": slot.id,
        "day_of_week": slot.day_of_week,
        "start_time": slot.start_time.strftime("%H:%M"),
        "end_time": slot.end_time.strftime("%H:%M"),
        "label": slot.label,
    }


_DAY_NAMES = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]

# Plages standard de l'établissement :
# - 08h00-12h00 : cours du matin, commun à tous les niveaux.
# - 13h00-17h00 : cours de l'après-midi, Bachelor 1 et 2.
# - 18h00-22h00 : cours du soir, Bachelor 3, Master 1 et 2 (pas de cours
#   l'après-midi pour ce groupe — programme en alternance).
STANDARD_TIMESLOT_PRESET_BANDS: list[tuple[time, time, str]] = [
    (time(8, 0), time(12, 0), ""),
    (time(13, 0), time(17, 0), " (B1-B2)"),
    (time(18, 0), time(22, 0), " (B3-M1-M2)"),
]


class TimeSlotPresetsIn(BaseModel):
    days: list[int] = Field(min_length=1, description="0=lundi … 6=dimanche")

    @field_validator("days")
    @classmethod
    def validate_days(cls, value: list[int]) -> list[int]:
        for day in value:
            if not 0 <= day <= 6:
                raise ValueError("Jour invalide (0=lundi … 6=dimanche)")
        return sorted(set(value))


async def apply_standard_timeslot_presets_to_session(
    session: AsyncSession, days: list[int]
) -> list[TimeSlot]:
    """Crée, de façon idempotente, les plages horaires standard pour les
    jours donnés (créneaux déjà présents — même jour et mêmes horaires —
    ignorés, donc rappelable sans créer de doublons)."""
    existing = {
        (s.day_of_week, s.start_time, s.end_time)
        for s in (await session.execute(select(TimeSlot))).scalars().all()
    }
    for day in days:
        for start, end, suffix in STANDARD_TIMESLOT_PRESET_BANDS:
            key = (day, start, end)
            if key in existing:
                continue
            session.add(
                TimeSlot(
                    day_of_week=day,
                    start_time=start,
                    end_time=end,
                    label=(
                        f"{_DAY_NAMES[day]} {start.strftime('%Hh%M')}-"
                        f"{end.strftime('%Hh%M')}{suffix}"
                    ),
                )
            )
            existing.add(key)
    await session.commit()
    rows = (
        await session.execute(
            select(TimeSlot)
            .where(TimeSlot.day_of_week.in_(days))
            .order_by(TimeSlot.day_of_week, TimeSlot.start_time)
        )
    ).scalars().all()
    return list(rows)


@router.post(
    "/admin/timeslots/apply-standard-presets", response_model=list[TimeSlotOut]
)
async def apply_standard_timeslot_presets(
    body: TimeSlotPresetsIn,
    _user: AdminUser = Depends(require_admin_write),
    session: AsyncSession = Depends(get_db),
) -> list[dict]:
    rows = await apply_standard_timeslot_presets_to_session(session, body.days)
    return [_serialize_timeslot(s) for s in rows]


@router.get("/admin/timeslots", response_model=list[TimeSlotOut])
async def list_timeslots(
    _user: AdminUser = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db),
) -> list[dict]:
    rows = (
        await session.execute(select(TimeSlot).order_by(TimeSlot.day_of_week, TimeSlot.start_time))
    ).scalars().all()
    return [_serialize_timeslot(s) for s in rows]


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
    return _serialize_timeslot(slot)


@router.patch("/admin/timeslots/{timeslot_id}", response_model=TimeSlotOut)
async def update_timeslot(
    timeslot_id: int,
    body: TimeSlotIn,
    _user: AdminUser = Depends(require_admin_write),
    session: AsyncSession = Depends(get_db),
) -> dict:
    slot = await session.get(TimeSlot, timeslot_id)
    if slot is None:
        raise HTTPException(status_code=404, detail="Créneau introuvable")
    slot.day_of_week = body.day_of_week
    slot.start_time = _parse_time(body.start_time)
    slot.end_time = _parse_time(body.end_time)
    slot.label = body.label
    await session.commit()
    await session.refresh(slot)
    return _serialize_timeslot(slot)


@router.delete("/admin/timeslots/{timeslot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_timeslot(
    timeslot_id: int,
    _user: AdminUser = Depends(require_admin_write),
    session: AsyncSession = Depends(get_db),
) -> None:
    slot = await session.get(TimeSlot, timeslot_id)
    if slot is None:
        raise HTTPException(status_code=404, detail="Créneau introuvable")
    in_use = await session.scalar(
        select(ScheduleEntry.id).where(ScheduleEntry.timeslot_id == timeslot_id).limit(1)
    )
    if in_use is not None:
        raise HTTPException(
            status_code=409,
            detail="Créneau utilisé par au moins une séance planifiée ; "
            "retirez ou déplacez ces séances avant de le supprimer.",
        )
    await session.delete(slot)
    await session.commit()


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
            "group_name": (
                strip_level_code(e.course.group.name)
                if e.course and e.course.group
                else None
            ),
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


@router.delete("/admin/schedule/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule_entry(
    entry_id: int,
    _user: AdminUser = Depends(require_admin_write),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Suppression définitive d'une séance.

    Distincte de /cancel (annulation douce, conserve la ligne et son
    historique). Bloquée si des propositions de changement (ScheduleChange)
    référencent encore cette séance, afin de ne pas casser la traçabilité
    des demandes de report en cours ou déjà traitées : annulez la séance,
    ou traitez/supprimez ces propositions d'abord.
    """
    entry = await session.get(ScheduleEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Séance introuvable")
    linked_change = await session.scalar(
        select(ScheduleChange.id).where(ScheduleChange.entry_id == entry_id).limit(1)
    )
    if linked_change is not None:
        raise HTTPException(
            status_code=409,
            detail="Des propositions de changement référencent encore cette séance ; "
            "annulez-la (statut cancelled) plutôt que de la supprimer, ou "
            "traitez ces propositions d'abord.",
        )
    await session.delete(entry)
    await session.commit()


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
