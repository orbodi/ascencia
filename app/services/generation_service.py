from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.models import (
    AuditLog,
    Availability,
    Course,
    PresenceCampaign,
    PresenceCampaignStatus,
    PublicationStatus,
    Room,
    ScheduleEntry,
    ScheduleEntryStatus,
    SchedulePublication,
    TimeSlot,
)
from app.config import settings
from app.services.academic_calendar import academic_week_number
from app.services.curriculum_service import CurriculumService
from app.services.planning_rules import (
    BlockingAvailability,
    CandidateCheck,
    OccupiedEntry,
    SlotWindow,
    detect_conflicts,
)
from app.services.planning_service import PlanningService


class ScheduleGenerationService:
    """Génère un brouillon hebdomadaire par contraintes et score heuristique."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def generate_draft(
        self, week_start: date, *, created_by: str
    ) -> SchedulePublication:
        monday = week_start - timedelta(days=week_start.weekday())
        sunday = monday + timedelta(days=6)
        week_number = academic_week_number(monday)

        courses = (
            await self.session.execute(
                select(Course)
                .options(
                    selectinload(Course.teacher),
                    selectinload(Course.group),
                )
                .order_by(Course.priority.desc(), Course.id)
            )
        ).scalars().all()
        rooms = (
            await self.session.execute(select(Room).order_by(Room.capacity, Room.name))
        ).scalars().all()
        slots = (
            await self.session.execute(
                select(TimeSlot).order_by(TimeSlot.day_of_week, TimeSlot.start_time)
            )
        ).scalars().all()

        week_entries = (
            await self.session.execute(
                select(ScheduleEntry)
                .where(
                    ScheduleEntry.entry_date >= monday,
                    ScheduleEntry.entry_date <= sunday,
                )
                .options(
                    selectinload(ScheduleEntry.course).selectinload(Course.teacher),
                    selectinload(ScheduleEntry.course).selectinload(Course.group),
                    selectinload(ScheduleEntry.room),
                    selectinload(ScheduleEntry.timeslot),
                )
            )
        ).scalars().all()
        occupied = [
            OccupiedEntry(
                entry_id=entry.id,
                teacher_id=entry.course.teacher_id,
                group_id=entry.course.group_id,
                room_id=entry.room_id,
                window=SlotWindow(
                    entry.entry_date,
                    entry.timeslot.start_time,
                    entry.timeslot.end_time,
                ),
                status=entry.status.value,
            )
            for entry in week_entries
            if entry.status == ScheduleEntryStatus.scheduled
        ]
        reserved_room_slots = {
            (entry.entry_date, entry.timeslot_id, entry.room_id)
            for entry in week_entries
        }
        existing_snapshot = [
            {
                "course_id": entry.course_id,
                "course_title": entry.course.title,
                "teacher_id": entry.course.teacher_id,
                "teacher_name": entry.course.teacher.name,
                "group_id": entry.course.group_id,
                "group_name": entry.course.group.name,
                "room_id": entry.room_id,
                "room_name": entry.room.name,
                "timeslot_id": entry.timeslot_id,
                "timeslot_label": entry.timeslot.label,
                "entry_date": entry.entry_date.isoformat(),
                "is_new": False,
            }
            for entry in week_entries
            if entry.status == ScheduleEntryStatus.scheduled
        ]
        sessions_in_week: Counter[int] = Counter(
            entry.course_id
            for entry in week_entries
            if entry.status == ScheduleEntryStatus.scheduled
        )

        (
            intentions,
            levels_under_plan,
            curriculum_warnings,
        ) = await CurriculumService(self.session).intentions_for_week(week_number)

        blocks = [
            BlockingAvailability(
                teacher_id=item.teacher_id,
                start_at=item.start_at,
                end_at=item.end_at,
                reason=item.reason,
            )
            for item in (
                await self.session.execute(
                    select(Availability).where(Availability.is_blocking.is_(True))
                )
            ).scalars().all()
        ]
        scheduled_counts = dict(
            (
                await self.session.execute(
                    select(ScheduleEntry.course_id, func.count(ScheduleEntry.id))
                    .where(ScheduleEntry.status == ScheduleEntryStatus.scheduled)
                    .group_by(ScheduleEntry.course_id)
                )
            ).all()
        )
        course_by_id = {course.id: course for course in courses}

        day_load: Counter[date] = Counter(entry.entry_date for entry in week_entries)
        teacher_day_load: Counter[tuple[int, date]] = Counter(
            (entry.course.teacher_id, entry.entry_date)
            for entry in week_entries
            if entry.status == ScheduleEntryStatus.scheduled
        )
        group_day_load: Counter[tuple[int, date]] = Counter(
            (entry.course.group_id, entry.entry_date)
            for entry in week_entries
            if entry.status == ScheduleEntryStatus.scheduled
        )
        group_day_minutes: Counter[tuple[int, date]] = Counter()
        for entry in week_entries:
            if entry.status == ScheduleEntryStatus.scheduled:
                group_day_minutes[(entry.course.group_id, entry.entry_date)] += (
                    entry.course.duration_minutes
                )

        generated: list[dict[str, Any]] = []
        unscheduled: list[dict[str, Any]] = []
        skipped_complete = 0
        skipped_not_in_plan = 0
        curriculum_mode_used = bool(levels_under_plan)

        def sessions_needed_for(course: Course) -> int | None:
            """None = skip (not in plan); 0+ = place that many this week."""
            level_id = course.group.academic_level_id if course.group else None
            if level_id is not None and level_id in levels_under_plan:
                return intentions.get(course.id, 0)
            # Fallback volume: one session if volume incomplete
            completed = scheduled_counts.get(course.id, 0) * course.duration_minutes
            if completed >= course.planned_minutes:
                return None  # signal complete via separate path
            return 1

        for course in courses:
            completed_minutes = (
                scheduled_counts.get(course.id, 0) * course.duration_minutes
            )
            level_id = course.group.academic_level_id if course.group else None
            under_plan = level_id is not None and level_id in levels_under_plan

            if not under_plan and completed_minutes >= course.planned_minutes:
                skipped_complete += 1
                continue

            needed = sessions_needed_for(course)
            if needed is None:
                skipped_complete += 1
                continue
            if needed == 0:
                skipped_not_in_plan += 1
                continue

            if course.prerequisite_course_id:
                prerequisite = course_by_id.get(course.prerequisite_course_id)
                prerequisite_done = scheduled_counts.get(
                    course.prerequisite_course_id, 0
                ) * (prerequisite.duration_minutes if prerequisite else 0)
                if (
                    prerequisite is None
                    or prerequisite_done < prerequisite.planned_minutes
                ):
                    unscheduled.append(
                        {
                            "course_id": course.id,
                            "course_title": course.title,
                            "reason": "Le prérequis pédagogique n'est pas encore achevé.",
                            "sessions_requested": needed,
                        }
                    )
                    continue

            remaining = max(0, needed - sessions_in_week[course.id])
            if remaining == 0:
                continue

            placed = 0
            for _ in range(remaining):
                candidates: list[tuple[int, date, TimeSlot, Room]] = []
                for slot in slots:
                    target_date = monday + timedelta(days=slot.day_of_week)
                    if target_date > sunday:
                        continue
                    slot_minutes = (
                        slot.end_time.hour * 60
                        + slot.end_time.minute
                        - slot.start_time.hour * 60
                        - slot.start_time.minute
                    )
                    if course.duration_minutes > slot_minutes:
                        continue
                    if (
                        group_day_minutes[(course.group_id, target_date)]
                        + course.duration_minutes
                        > settings.max_group_daily_minutes
                    ):
                        continue
                    for room in rooms:
                        if (target_date, slot.id, room.id) in reserved_room_slots:
                            continue
                        candidate = CandidateCheck(
                            teacher_id=course.teacher_id,
                            group_id=course.group_id,
                            room_id=room.id,
                            room_capacity=room.capacity,
                            student_count=course.group.student_count,
                            window=SlotWindow(
                                target_date, slot.start_time, slot.end_time
                            ),
                        )
                        if detect_conflicts(candidate, occupied, blocks):
                            continue
                        score = (
                            day_load[target_date] * 100
                            + teacher_day_load[(course.teacher_id, target_date)] * 60
                            + group_day_load[(course.group_id, target_date)] * 60
                            + max(room.capacity - course.group.student_count, 0)
                            + slot.start_time.hour
                        )
                        candidates.append((score, target_date, slot, room))

                if not candidates:
                    break

                _, target_date, slot, room = min(
                    candidates,
                    key=lambda item: (
                        item[0],
                        item[1],
                        item[2].start_time,
                        item[3].name,
                    ),
                )
                draft_id = -len(generated) - 1
                occupied.append(
                    OccupiedEntry(
                        entry_id=draft_id,
                        teacher_id=course.teacher_id,
                        group_id=course.group_id,
                        room_id=room.id,
                        window=SlotWindow(
                            target_date, slot.start_time, slot.end_time
                        ),
                        status="draft",
                    )
                )
                reserved_room_slots.add((target_date, slot.id, room.id))
                day_load[target_date] += 1
                teacher_day_load[(course.teacher_id, target_date)] += 1
                group_day_load[(course.group_id, target_date)] += 1
                group_day_minutes[(course.group_id, target_date)] += (
                    course.duration_minutes
                )
                sessions_in_week[course.id] += 1
                placed += 1
                generated.append(
                    {
                        "course_id": course.id,
                        "course_title": course.title,
                        "teacher_id": course.teacher_id,
                        "teacher_name": course.teacher.name,
                        "group_id": course.group_id,
                        "group_name": course.group.name,
                        "room_id": room.id,
                        "room_name": room.name,
                        "timeslot_id": slot.id,
                        "timeslot_label": slot.label,
                        "entry_date": target_date.isoformat(),
                        "is_new": True,
                    }
                )

            if placed < remaining:
                unscheduled.append(
                    {
                        "course_id": course.id,
                        "course_title": course.title,
                        "reason": "Aucun créneau compatible avec les contraintes actuelles.",
                        "sessions_requested": needed,
                        "sessions_placed": placed + (needed - remaining),
                        "sessions_missing": remaining - placed,
                    }
                )

        sequence = (
            await self.session.scalar(
                select(func.count())
                .select_from(SchedulePublication)
                .where(SchedulePublication.week_start == monday)
            )
            or 0
        ) + 1
        version = f"EDT-{monday.strftime('%Y%m%d')}-V{sequence}"
        notice = (
            "Brouillon calculé par règles déterministes et score d'équilibrage. "
            "Une validation humaine reste obligatoire."
        )
        if curriculum_mode_used:
            notice = (
                f"Programme pédagogique actif (semaine académique {week_number}). "
                + notice
            )
        elif curriculum_warnings:
            notice = "Fallback volume (hors horizon programme). " + notice

        report = {
            "engine": "heuristic-constraints-v1",
            "academic_week_number": week_number,
            "curriculum_mode": curriculum_mode_used,
            "curriculum_warnings": curriculum_warnings,
            "intentions": intentions,
            "generated_count": len(generated),
            "unscheduled_count": len(unscheduled),
            "skipped_complete_count": skipped_complete,
            "skipped_not_in_plan_count": skipped_not_in_plan,
            "unscheduled": unscheduled,
            "notice": notice,
        }
        publication = SchedulePublication(
            version_number=version,
            week_start=monday,
            week_end=sunday,
            status=PublicationStatus.draft,
            snapshot_json=sorted(
                existing_snapshot + generated,
                key=lambda item: (
                    item["entry_date"],
                    item["timeslot_id"],
                    item["group_name"],
                ),
            ),
            generation_report=report,
            created_by=created_by,
        )
        self.session.add(publication)
        self.session.add(
            AuditLog(
                action="schedule_draft_generated",
                payload={
                    "version": version,
                    "week_start": monday.isoformat(),
                    **report,
                },
            )
        )
        await self.session.commit()
        await self.session.refresh(publication)
        return publication

    async def publish(
        self,
        publication_id: int,
        *,
        published_by: str,
        force_presence_override: bool = False,
    ) -> SchedulePublication:
        publication = await self.session.get(SchedulePublication, publication_id)
        if publication is None:
            raise ValueError("Version de planning introuvable")
        if publication.status != PublicationStatus.draft:
            raise ValueError("Seul un brouillon peut être publié")
        if not publication.snapshot_json:
            raise ValueError("Ce brouillon ne contient aucune séance publiable")

        campaign = await self.session.scalar(
            select(PresenceCampaign).where(
                PresenceCampaign.publication_id == publication_id
            )
        )
        if campaign is None and not force_presence_override:
            raise ValueError(
                "La campagne de confirmation des enseignants n'a pas été créée"
            )
        if (
            campaign is not None
            and campaign.status != PresenceCampaignStatus.ready
            and not force_presence_override
        ):
            raise ValueError(
                "La publication est bloquée : toutes les présences ne sont pas "
                f"confirmées (statut={campaign.status.value})"
            )

        planning = PlanningService(self.session)
        for item in publication.snapshot_json:
            if item.get("is_new") is False:
                continue
            conflicts = await planning.validate_schedule_entry(
                course_id=int(item["course_id"]),
                room_id=int(item["room_id"]),
                timeslot_id=int(item["timeslot_id"]),
                entry_date=date.fromisoformat(item["entry_date"]),
            )
            if conflicts:
                details = "; ".join(conflict["message"] for conflict in conflicts)
                await self.session.rollback()
                raise ValueError(
                    f"Publication interrompue pour « {item['course_title']} » : {details}"
                )
            self.session.add(
                ScheduleEntry(
                    course_id=int(item["course_id"]),
                    room_id=int(item["room_id"]),
                    timeslot_id=int(item["timeslot_id"]),
                    entry_date=date.fromisoformat(item["entry_date"]),
                    status=ScheduleEntryStatus.scheduled,
                )
            )
            await self.session.flush()

        previous = (
            await self.session.execute(
                select(SchedulePublication).where(
                    SchedulePublication.week_start == publication.week_start,
                    SchedulePublication.status == PublicationStatus.published,
                    SchedulePublication.id != publication.id,
                )
            )
        ).scalars().all()
        for item in previous:
            item.status = PublicationStatus.archived

        publication.status = PublicationStatus.published
        publication.published_by = published_by
        publication.published_at = datetime.now(timezone.utc)
        if campaign is not None:
            campaign.status = PresenceCampaignStatus.completed
            campaign.completed_at = datetime.now(timezone.utc)
        self.session.add(
            AuditLog(
                action="schedule_published",
                payload={
                    "publication_id": publication.id,
                    "version": publication.version_number,
                    "published_by": published_by,
                    "entries_count": len(publication.snapshot_json),
                    "presence_override": force_presence_override,
                },
            )
        )
        await self.session.commit()
        await self.session.refresh(publication)
        return publication

    async def list_publications(self) -> list[SchedulePublication]:
        return list(
            (
                await self.session.execute(
                    select(SchedulePublication).order_by(SchedulePublication.id.desc())
                )
            ).scalars().all()
        )
