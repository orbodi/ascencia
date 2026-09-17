"""Services planning (lecture / propositions / application)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.models import (
    AuditLog,
    Availability,
    Course,
    Room,
    ScheduleChange,
    ScheduleChangeStatus,
    ScheduleEntry,
    ScheduleEntryStatus,
    Teacher,
    TimeSlot,
)
from app.services.display import strip_level_code
from app.services.planning_rules import (
    BlockingAvailability,
    CandidateCheck,
    OccupiedEntry,
    SlotWindow,
    detect_conflicts,
)


class PlanningService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_teacher(self, teacher_id: int) -> Teacher | None:
        return await self.session.get(Teacher, teacher_id)

    async def get_teacher_by_phone(self, phone: str) -> Teacher | None:
        result = await self.session.execute(
            select(Teacher).where(Teacher.phone_whatsapp == phone)
        )
        return result.scalar_one_or_none()

    async def list_courses(self) -> list[dict[str, Any]]:
        result = await self.session.execute(
            select(Course)
            .options(selectinload(Course.teacher), selectinload(Course.group))
            .order_by(Course.id)
        )
        courses = result.scalars().all()

        entries_result = await self.session.execute(
            select(ScheduleEntry).where(
                ScheduleEntry.status == ScheduleEntryStatus.scheduled
            )
        )
        entries = entries_result.scalars().all()
        sessions_by_course: dict[int, int] = {}
        for entry in entries:
            sessions_by_course[entry.course_id] = (
                sessions_by_course.get(entry.course_id, 0) + 1
            )

        return [
            {
                "id": c.id,
                "title": c.title,
                "teacher_id": c.teacher_id,
                "teacher_name": c.teacher.name if c.teacher else None,
                "group_id": c.group_id,
                "group_name": strip_level_code(c.group.name) if c.group else None,
                "duration_minutes": c.duration_minutes,
                "duration_hours": self._format_hours(c.duration_minutes),
                "planned_hours": self._format_hours(c.planned_minutes),
                "scheduled_sessions": sessions_by_course.get(c.id, 0),
                "hours_done": self._format_hours(
                    sessions_by_course.get(c.id, 0) * c.duration_minutes
                ),
                "hours_remaining": self._format_hours(
                    max(
                        0,
                        c.planned_minutes
                        - sessions_by_course.get(c.id, 0) * c.duration_minutes,
                    )
                ),
            }
            for c in courses
        ]

    async def list_schedule(
        self,
        day: date | None = None,
        week_start: date | None = None,
        period: str | None = None,
    ) -> dict[str, Any]:
        start: date | None = None
        end: date | None = None
        label = "all"

        if day is not None:
            start = end = day
            label = day.isoformat()
        elif period in {"current_week", "next_week"} or week_start is not None:
            today = date.today()
            monday = today - timedelta(days=today.weekday())
            if period == "next_week":
                monday = monday + timedelta(days=7)
                label = "next_week"
            elif period == "current_week":
                label = "current_week"
            if week_start is not None:
                monday = week_start - timedelta(days=week_start.weekday())
                label = f"week_{monday.isoformat()}"
            start = monday
            end = monday + timedelta(days=6)

        stmt = (
            select(ScheduleEntry)
            .where(ScheduleEntry.status == ScheduleEntryStatus.scheduled)
            .options(
                selectinload(ScheduleEntry.course).selectinload(Course.group),
                selectinload(ScheduleEntry.course).selectinload(Course.teacher),
                selectinload(ScheduleEntry.room),
                selectinload(ScheduleEntry.timeslot),
            )
            .order_by(ScheduleEntry.entry_date, ScheduleEntry.timeslot_id)
        )
        if start is not None and end is not None:
            stmt = stmt.where(
                ScheduleEntry.entry_date >= start,
                ScheduleEntry.entry_date <= end,
            )

        rows = (await self.session.execute(stmt)).scalars().all()
        return {
            "period": label,
            "from": start.isoformat() if start else None,
            "to": end.isoformat() if end else None,
            "entries": [self._serialize_entry(e) for e in rows],
            "count": len(rows),
        }

    async def get_teacher_schedule(
        self, teacher_id: int, day: date | None = None
    ) -> list[dict[str, Any]]:
        stmt = (
            select(ScheduleEntry)
            .join(Course)
            .where(
                Course.teacher_id == teacher_id,
                ScheduleEntry.status == ScheduleEntryStatus.scheduled,
            )
            .options(
                selectinload(ScheduleEntry.course).selectinload(Course.group),
                selectinload(ScheduleEntry.course).selectinload(Course.teacher),
                selectinload(ScheduleEntry.room),
                selectinload(ScheduleEntry.timeslot),
            )
            .order_by(ScheduleEntry.entry_date, ScheduleEntry.timeslot_id)
        )
        if day is not None:
            stmt = stmt.where(ScheduleEntry.entry_date == day)

        rows = (await self.session.execute(stmt)).scalars().all()
        return [self._serialize_entry(e) for e in rows]

    async def get_teacher_availability(self, teacher_id: int) -> list[dict[str, Any]]:
        result = await self.session.execute(
            select(Availability)
            .where(Availability.teacher_id == teacher_id)
            .order_by(Availability.start_at)
        )
        return [
            {
                "id": a.id,
                "teacher_id": a.teacher_id,
                "start_at": a.start_at.isoformat(),
                "end_at": a.end_at.isoformat(),
                "reason": a.reason,
                "is_blocking": a.is_blocking,
            }
            for a in result.scalars().all()
        ]

    async def update_teacher_availability(
        self,
        teacher_id: int,
        start_at: datetime,
        end_at: datetime,
        reason: str | None = None,
        is_blocking: bool = True,
    ) -> dict[str, Any]:
        if end_at <= start_at:
            raise ValueError("end_at doit être après start_at")

        teacher = await self.get_teacher(teacher_id)
        if teacher is None:
            raise ValueError(f"Enseignant #{teacher_id} introuvable")

        availability = Availability(
            teacher_id=teacher_id,
            start_at=start_at,
            end_at=end_at,
            reason=reason,
            is_blocking=is_blocking,
        )
        self.session.add(availability)
        self.session.add(
            AuditLog(
                action="update_teacher_availability",
                payload={
                    "teacher_id": teacher_id,
                    "start_at": start_at.isoformat(),
                    "end_at": end_at.isoformat(),
                    "reason": reason,
                },
            )
        )
        await self.session.commit()
        await self.session.refresh(availability)
        return {
            "id": availability.id,
            "teacher_id": teacher_id,
            "start_at": availability.start_at.isoformat(),
            "end_at": availability.end_at.isoformat(),
            "reason": availability.reason,
        }

    async def find_impacted_entries(
        self, teacher_id: int, day: date
    ) -> list[dict[str, Any]]:
        return await self.get_teacher_schedule(teacher_id, day=day)

    async def find_available_slots(
        self,
        entry_id: int,
        search_start: date,
        search_end: date,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        entry = await self._load_entry(entry_id)
        if entry is None:
            raise ValueError(f"Séance #{entry_id} introuvable")

        slots = (
            await self.session.execute(select(TimeSlot).order_by(TimeSlot.id))
        ).scalars().all()
        rooms = (await self.session.execute(select(Room))).scalars().all()
        occupied = await self._occupied_entries(search_start, search_end)
        blocks = await self._blocking_availabilities(entry.course.teacher_id)

        options: list[dict[str, Any]] = []
        current = search_start
        while current <= search_end and len(options) < limit:
            dow = current.weekday()
            day_slots = [s for s in slots if s.day_of_week == dow]
            for slot in day_slots:
                for room in rooms:
                    candidate = CandidateCheck(
                        teacher_id=entry.course.teacher_id,
                        group_id=entry.course.group_id,
                        room_id=room.id,
                        room_capacity=room.capacity,
                        student_count=entry.course.group.student_count,
                        window=SlotWindow(current, slot.start_time, slot.end_time),
                        ignore_entry_id=entry.id,
                    )
                    conflicts = detect_conflicts(candidate, occupied, blocks)
                    if conflicts:
                        continue
                    # éviter de reproposer le même créneau exact
                    if (
                        current == entry.entry_date
                        and slot.id == entry.timeslot_id
                        and room.id == entry.room_id
                    ):
                        continue
                    options.append(
                        {
                            "entry_id": entry.id,
                            "entry_date": current.isoformat(),
                            "timeslot_id": slot.id,
                            "timeslot_label": slot.label,
                            "room_id": room.id,
                            "room_name": room.name,
                            "summary": (
                                f"{current.isoformat()} · {slot.label} · {room.name}"
                            ),
                        }
                    )
                    if len(options) >= limit:
                        break
                if len(options) >= limit:
                    break
            current += timedelta(days=1)
        return options

    async def detect_conflicts_for_move(
        self,
        entry_id: int,
        entry_date: date,
        timeslot_id: int,
        room_id: int,
    ) -> list[dict[str, str]]:
        entry = await self._load_entry(entry_id)
        if entry is None:
            raise ValueError(f"Séance #{entry_id} introuvable")
        slot = await self.session.get(TimeSlot, timeslot_id)
        room = await self.session.get(Room, room_id)
        if slot is None or room is None:
            raise ValueError("Créneau ou salle introuvable")

        occupied = await self._occupied_entries(entry_date, entry_date)
        blocks = await self._blocking_availabilities(entry.course.teacher_id)
        candidate = CandidateCheck(
            teacher_id=entry.course.teacher_id,
            group_id=entry.course.group_id,
            room_id=room.id,
            room_capacity=room.capacity,
            student_count=entry.course.group.student_count,
            window=SlotWindow(entry_date, slot.start_time, slot.end_time),
            ignore_entry_id=entry.id,
        )
        return [
            {"code": c.code, "message": c.message}
            for c in detect_conflicts(candidate, occupied, blocks)
        ]

    async def validate_schedule_entry(
        self,
        *,
        course_id: int,
        room_id: int,
        timeslot_id: int,
        entry_date: date,
        ignore_entry_id: int | None = None,
    ) -> list[dict[str, str]]:
        """Contrôle une création ou une modification manuelle avant écriture."""
        course = await self.session.scalar(
            select(Course)
            .where(Course.id == course_id)
            .options(selectinload(Course.group), selectinload(Course.teacher))
        )
        room = await self.session.get(Room, room_id)
        slot = await self.session.get(TimeSlot, timeslot_id)
        if course is None:
            raise ValueError("Cours introuvable")
        if room is None:
            raise ValueError("Salle introuvable")
        if slot is None:
            raise ValueError("Créneau introuvable")
        if slot.day_of_week != entry_date.weekday():
            return [{
                "code": "timeslot_day_mismatch",
                "message": "Le jour de la date ne correspond pas au jour du créneau.",
            }]

        slot_minutes = (
            slot.end_time.hour * 60
            + slot.end_time.minute
            - slot.start_time.hour * 60
            - slot.start_time.minute
        )
        if course.duration_minutes > slot_minutes:
            return [{
                "code": "course_too_long",
                "message": (
                    f"Le cours dure {course.duration_minutes} minutes, mais le créneau "
                    f"n'en contient que {slot_minutes}."
                ),
            }]

        exact_stmt = select(ScheduleEntry.id).where(
            ScheduleEntry.room_id == room_id,
            ScheduleEntry.timeslot_id == timeslot_id,
            ScheduleEntry.entry_date == entry_date,
        )
        if ignore_entry_id is not None:
            exact_stmt = exact_stmt.where(ScheduleEntry.id != ignore_entry_id)
        if await self.session.scalar(exact_stmt):
            return [{
                "code": "room_slot_reserved",
                "message": "Cette salle possède déjà une séance pour ce créneau.",
            }]

        occupied = await self._occupied_entries(entry_date, entry_date)
        blocks = await self._blocking_availabilities(course.teacher_id)
        candidate = CandidateCheck(
            teacher_id=course.teacher_id,
            group_id=course.group_id,
            room_id=room.id,
            room_capacity=room.capacity,
            student_count=course.group.student_count,
            window=SlotWindow(entry_date, slot.start_time, slot.end_time),
            ignore_entry_id=ignore_entry_id,
        )
        return [
            {"code": conflict.code, "message": conflict.message}
            for conflict in detect_conflicts(candidate, occupied, blocks)
        ]

    async def propose_move_course(
        self,
        entry_id: int,
        entry_date: date,
        timeslot_id: int,
        room_id: int,
        proposed_by: str = "agent",
    ) -> dict[str, Any]:
        conflicts = await self.detect_conflicts_for_move(
            entry_id, entry_date, timeslot_id, room_id
        )
        if conflicts:
            return {"ok": False, "conflicts": conflicts}

        entry = await self._load_entry(entry_id)
        assert entry is not None
        before = self._serialize_entry(entry)
        after = {
            **before,
            "entry_date": entry_date.isoformat(),
            "timeslot_id": timeslot_id,
            "room_id": room_id,
        }
        change = ScheduleChange(
            entry_id=entry_id,
            before_json=before,
            after_json=after,
            status=ScheduleChangeStatus.proposed,
            proposed_by=proposed_by,
        )
        self.session.add(change)
        self.session.add(
            AuditLog(
                action="propose_move_course",
                payload={"entry_id": entry_id, "after": after, "proposed_by": proposed_by},
            )
        )
        await self.session.commit()
        await self.session.refresh(change)
        return {
            "ok": True,
            "change_id": change.id,
            "status": change.status.value,
            "before": before,
            "after": after,
        }

    async def apply_schedule_change(self, change_id: int) -> dict[str, Any]:
        change = await self.session.get(ScheduleChange, change_id)
        if change is None:
            raise ValueError(f"Changement #{change_id} introuvable")
        if change.status != ScheduleChangeStatus.approved:
            raise ValueError(
                f"Changement #{change_id} non applicable : une approbation humaine "
                "est obligatoire avant l'application."
            )
        entry = await self._load_entry(change.entry_id)
        if entry is None:
            raise ValueError("Séance liée introuvable")

        after = change.after_json
        conflicts = await self.detect_conflicts_for_move(
            change.entry_id,
            date.fromisoformat(after["entry_date"]),
            int(after["timeslot_id"]),
            int(after["room_id"]),
        )
        if conflicts:
            messages = "; ".join(item["message"] for item in conflicts)
            raise ValueError(f"Le changement n'est plus applicable : {messages}")
        entry.entry_date = date.fromisoformat(after["entry_date"])
        entry.timeslot_id = int(after["timeslot_id"])
        entry.room_id = int(after["room_id"])
        entry.status = ScheduleEntryStatus.scheduled

        change.status = ScheduleChangeStatus.applied
        change.decided_at = datetime.now(timezone.utc)
        self.session.add(
            AuditLog(
                action="apply_schedule_change",
                payload={
                    "change_id": change_id,
                    "entry_id": entry.id,
                    "teacher_id": entry.course.teacher_id,
                    "course_title": entry.course.title,
                    "entry_date": entry.entry_date.isoformat(),
                    "after": after,
                },
            )
        )
        await self.session.commit()
        return {
            "ok": True,
            "change_id": change_id,
            "entry": self._serialize_entry(entry),
        }

    async def approve_schedule_change(
        self, change_id: int, *, approved_by: str = "admin"
    ) -> dict[str, Any]:
        change = await self.session.get(ScheduleChange, change_id)
        if change is None:
            raise ValueError(f"Changement #{change_id} introuvable")
        if change.status != ScheduleChangeStatus.proposed:
            raise ValueError("Seuls les changements proposed peuvent être approuvés")
        change.status = ScheduleChangeStatus.approved
        change.decided_at = datetime.now(timezone.utc)
        self.session.add(
            AuditLog(
                action="approve_schedule_change",
                payload={"change_id": change_id, "approved_by": approved_by},
            )
        )
        await self.session.commit()
        return {
            "ok": True,
            "change_id": change_id,
            "status": change.status.value,
            "approved_by": approved_by,
        }

    async def confirm_presence(
        self, entry_id: int, teacher_id: int | None = None
    ) -> dict[str, Any]:
        entry = await self._load_entry(entry_id)
        if entry is None:
            raise ValueError(f"Séance #{entry_id} introuvable")
        if entry.status != ScheduleEntryStatus.scheduled:
            raise ValueError(
                f"Séance #{entry_id} non confirmable (statut={entry.status.value})"
            )
        if teacher_id is not None and entry.course.teacher_id != teacher_id:
            raise ValueError("Cette séance n'appartient pas à cet enseignant")

        self.session.add(
            AuditLog(
                action="presence_confirmed",
                payload={
                    "entry_id": entry_id,
                    "teacher_id": entry.course.teacher_id,
                    "entry_date": entry.entry_date.isoformat(),
                    "course_title": entry.course.title,
                },
            )
        )
        await self.session.commit()
        return {
            "ok": True,
            "confirmed": True,
            "entry": self._serialize_entry(entry),
            "message": (
                f"Présence confirmée pour « {entry.course.title} » "
                f"le {entry.entry_date.isoformat()}."
            ),
        }

    async def cancel_course(
        self,
        entry_id: int,
        reason: str | None = None,
        teacher_id: int | None = None,
        propose_alternatives: bool = True,
        search_days: int = 7,
        limit: int = 3,
    ) -> dict[str, Any]:
        entry = await self._load_entry(entry_id)
        if entry is None:
            raise ValueError(f"Séance #{entry_id} introuvable")
        if entry.status != ScheduleEntryStatus.scheduled:
            raise ValueError(
                f"Séance #{entry_id} déjà {entry.status.value}"
            )
        if teacher_id is not None and entry.course.teacher_id != teacher_id:
            raise ValueError("Cette séance n'appartient pas à cet enseignant")

        before = self._serialize_entry(entry)
        entry.status = ScheduleEntryStatus.cancelled
        self.session.add(
            AuditLog(
                action="course_cancelled",
                payload={
                    "entry_id": entry_id,
                    "teacher_id": entry.course.teacher_id,
                    "reason": reason,
                    "before": before,
                },
            )
        )
        await self.session.commit()

        alternatives: list[dict[str, Any]] = []
        if propose_alternatives:
            alternatives = await self.find_available_slots(
                entry_id=entry_id,
                search_start=entry.entry_date + timedelta(days=1),
                search_end=entry.entry_date + timedelta(days=search_days),
                limit=limit,
            )

        return {
            "ok": True,
            "cancelled": True,
            "entry": self._serialize_entry(entry),
            "reason": reason,
            "alternatives": alternatives,
            "message": (
                "Séance annulée."
                + (
                    f" {len(alternatives)} créneau(x) alternatif(s) proposé(s)."
                    if alternatives
                    else " Aucune alternative trouvée automatiquement."
                )
            ),
        }

    async def _load_entry(self, entry_id: int) -> ScheduleEntry | None:
        result = await self.session.execute(
            select(ScheduleEntry)
            .where(ScheduleEntry.id == entry_id)
            .options(
                selectinload(ScheduleEntry.course).selectinload(Course.group),
                selectinload(ScheduleEntry.course).selectinload(Course.teacher),
                selectinload(ScheduleEntry.room),
                selectinload(ScheduleEntry.timeslot),
            )
        )
        return result.scalar_one_or_none()

    async def _occupied_entries(
        self, start: date, end: date
    ) -> list[OccupiedEntry]:
        result = await self.session.execute(
            select(ScheduleEntry)
            .where(
                ScheduleEntry.entry_date >= start,
                ScheduleEntry.entry_date <= end,
                ScheduleEntry.status == ScheduleEntryStatus.scheduled,
            )
            .options(
                selectinload(ScheduleEntry.course),
                selectinload(ScheduleEntry.timeslot),
            )
        )
        occupied: list[OccupiedEntry] = []
        for e in result.scalars().all():
            occupied.append(
                OccupiedEntry(
                    entry_id=e.id,
                    teacher_id=e.course.teacher_id,
                    group_id=e.course.group_id,
                    room_id=e.room_id,
                    window=SlotWindow(
                        e.entry_date, e.timeslot.start_time, e.timeslot.end_time
                    ),
                    status=e.status.value,
                )
            )
        return occupied

    async def _blocking_availabilities(
        self, teacher_id: int
    ) -> list[BlockingAvailability]:
        result = await self.session.execute(
            select(Availability).where(
                Availability.teacher_id == teacher_id,
                Availability.is_blocking.is_(True),
            )
        )
        return [
            BlockingAvailability(
                teacher_id=a.teacher_id,
                start_at=a.start_at,
                end_at=a.end_at,
                reason=a.reason,
            )
            for a in result.scalars().all()
        ]

    @staticmethod
    def _format_hours(minutes: int) -> str:
        hours = minutes / 60
        if hours == int(hours):
            return f"{int(hours)}H"
        # ex: 90 min -> 1H30
        whole = int(hours)
        mins = minutes % 60
        if whole == 0:
            return f"{mins}min"
        return f"{whole}H{mins:02d}"

    @staticmethod
    def _serialize_entry(entry: ScheduleEntry) -> dict[str, Any]:
        return {
            "id": entry.id,
            "course_id": entry.course_id,
            "course_title": entry.course.title if entry.course else None,
            "teacher_id": entry.course.teacher_id if entry.course else None,
            "teacher_name": (
                entry.course.teacher.name
                if entry.course and entry.course.teacher
                else None
            ),
            "group_id": entry.course.group_id if entry.course else None,
            "group_name": (
                strip_level_code(entry.course.group.name)
                if entry.course and entry.course.group
                else None
            ),
            "room_id": entry.room_id,
            "room_name": entry.room.name if entry.room else None,
            "timeslot_id": entry.timeslot_id,
            "timeslot_label": entry.timeslot.label if entry.timeslot else None,
            "entry_date": entry.entry_date.isoformat(),
            "status": entry.status.value,
        }
