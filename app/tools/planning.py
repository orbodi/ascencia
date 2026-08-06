"""Outils planning exposés à l'agent (wrappers JSON-friendly)."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.planning_service import PlanningService


async def get_teacher(session: AsyncSession, teacher_id: int) -> dict:
    teacher = await PlanningService(session).get_teacher(teacher_id)
    if teacher is None:
        return {"ok": False, "error": "Enseignant introuvable"}
    return {
        "ok": True,
        "teacher": {
            "id": teacher.id,
            "name": teacher.name,
            "email": teacher.email,
            "phone_whatsapp": teacher.phone_whatsapp,
        },
    }


async def list_courses(session: AsyncSession) -> dict:
    rows = await PlanningService(session).list_courses()
    return {"ok": True, "courses": rows, "count": len(rows)}


async def list_schedule(
    session: AsyncSession,
    day: str | None = None,
    week_start: str | None = None,
    period: str | None = None,
) -> dict:
    data = await PlanningService(session).list_schedule(
        day=date.fromisoformat(day) if day else None,
        week_start=date.fromisoformat(week_start) if week_start else None,
        period=period,
    )
    return {"ok": True, **data}


async def get_teacher_schedule(
    session: AsyncSession, teacher_id: int, day: str | None = None
) -> dict:
    parsed = date.fromisoformat(day) if day else None
    rows = await PlanningService(session).get_teacher_schedule(teacher_id, day=parsed)
    return {"ok": True, "entries": rows}


async def get_teacher_availability(session: AsyncSession, teacher_id: int) -> dict:
    rows = await PlanningService(session).get_teacher_availability(teacher_id)
    return {"ok": True, "availabilities": rows}


async def update_teacher_availability(
    session: AsyncSession,
    teacher_id: int,
    start_at: str,
    end_at: str,
    reason: str | None = None,
) -> dict:
    try:
        data = await PlanningService(session).update_teacher_availability(
            teacher_id=teacher_id,
            start_at=datetime.fromisoformat(start_at),
            end_at=datetime.fromisoformat(end_at),
            reason=reason,
        )
        return {"ok": True, "availability": data}
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}


async def find_impacted_entries(
    session: AsyncSession, teacher_id: int, day: str
) -> dict:
    rows = await PlanningService(session).find_impacted_entries(
        teacher_id, date.fromisoformat(day)
    )
    return {"ok": True, "entries": rows, "count": len(rows)}


async def find_available_slots(
    session: AsyncSession,
    entry_id: int,
    search_start: str,
    search_end: str,
    limit: int = 5,
) -> dict:
    try:
        options = await PlanningService(session).find_available_slots(
            entry_id=entry_id,
            search_start=date.fromisoformat(search_start),
            search_end=date.fromisoformat(search_end),
            limit=limit,
        )
        return {"ok": True, "options": options, "count": len(options)}
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}


async def detect_conflicts(
    session: AsyncSession,
    entry_id: int,
    entry_date: str,
    timeslot_id: int,
    room_id: int,
) -> dict:
    try:
        conflicts = await PlanningService(session).detect_conflicts_for_move(
            entry_id=entry_id,
            entry_date=date.fromisoformat(entry_date),
            timeslot_id=timeslot_id,
            room_id=room_id,
        )
        return {"ok": True, "conflicts": conflicts, "has_conflict": bool(conflicts)}
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}


async def propose_move_course(
    session: AsyncSession,
    entry_id: int,
    entry_date: str,
    timeslot_id: int,
    room_id: int,
    proposed_by: str = "agent",
) -> dict:
    try:
        return await PlanningService(session).propose_move_course(
            entry_id=entry_id,
            entry_date=date.fromisoformat(entry_date),
            timeslot_id=timeslot_id,
            room_id=room_id,
            proposed_by=proposed_by,
        )
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}


async def apply_schedule_change(session: AsyncSession, change_id: int) -> dict:
    try:
        return await PlanningService(session).apply_schedule_change(change_id)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}


async def confirm_presence(
    session: AsyncSession, entry_id: int, teacher_id: int | None = None
) -> dict:
    try:
        return await PlanningService(session).confirm_presence(entry_id, teacher_id)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}


async def cancel_course(
    session: AsyncSession,
    entry_id: int,
    reason: str | None = None,
    teacher_id: int | None = None,
    propose_alternatives: bool = True,
) -> dict:
    try:
        return await PlanningService(session).cancel_course(
            entry_id=entry_id,
            reason=reason,
            teacher_id=teacher_id,
            propose_alternatives=propose_alternatives,
        )
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}


async def generate_teacher_schedule_pdf(
    session: AsyncSession, teacher_id: int, week_start: str | None = None
) -> dict:
    from app.exporters import PdfExporter

    try:
        return await PdfExporter(session).generate_teacher_schedule_pdf(
            teacher_id,
            week_start=date.fromisoformat(week_start) if week_start else None,
        )
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"Erreur PDF: {exc}"}


async def generate_group_schedule_pdf(
    session: AsyncSession, group_id: int, week_start: str | None = None
) -> dict:
    from app.exporters import PdfExporter

    try:
        return await PdfExporter(session).generate_group_schedule_pdf(
            group_id,
            week_start=date.fromisoformat(week_start) if week_start else None,
        )
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"Erreur PDF: {exc}"}
