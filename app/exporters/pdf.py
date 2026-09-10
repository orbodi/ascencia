"""Export PDF des emplois du temps (Jinja2 + WeasyPrint)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from math import ceil
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.domain.models import Course, ScheduleEntry, ScheduleEntryStatus, StudentGroup, Teacher, TimeSlot

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
EXPORTS_DIR = Path(__file__).resolve().parents[2] / "exports"


class PdfExporter:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=select_autoescape(["html", "xml"]),
        )
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

    async def generate_teacher_schedule_pdf(
        self,
        teacher_id: int,
        week_start: date | None = None,
    ) -> dict[str, Any]:
        teacher = await self.session.get(Teacher, teacher_id)
        if teacher is None:
            raise ValueError(f"Enseignant #{teacher_id} introuvable")

        start, end, week_label = self._week_bounds(week_start)
        entries = await self._entries(
            start=start,
            end=end,
            teacher_id=teacher_id,
        )
        filename = f"planning_enseignant_{teacher_id}_{start.isoformat()}.pdf"
        path = await self._render_pdf(
            title=f"Emploi du temps — {teacher.name}",
            audience_label="Enseignant",
            audience_name=teacher.name,
            week_start=start,
            week_label=week_label,
            entries=entries,
            filename=filename,
        )
        return {
            "ok": True,
            "type": "teacher",
            "teacher_id": teacher_id,
            "teacher_name": teacher.name,
            "week_start": start.isoformat(),
            "week_end": end.isoformat(),
            "entries_count": len(entries),
            "path": str(path),
            "filename": filename,
        }

    async def generate_group_schedule_pdf(
        self,
        group_id: int,
        week_start: date | None = None,
    ) -> dict[str, Any]:
        group = await self.session.get(StudentGroup, group_id)
        if group is None:
            raise ValueError(f"Groupe #{group_id} introuvable")

        start, end, week_label = self._week_bounds(week_start)
        entries = await self._entries(start=start, end=end, group_id=group_id)
        filename = f"planning_groupe_{group_id}_{start.isoformat()}.pdf"
        path = await self._render_pdf(
            title=f"Emploi du temps — {group.name}",
            audience_label="Groupe",
            audience_name=group.name,
            week_start=start,
            week_label=week_label,
            entries=entries,
            filename=filename,
        )
        return {
            "ok": True,
            "type": "group",
            "group_id": group_id,
            "group_name": group.name,
            "week_start": start.isoformat(),
            "week_end": end.isoformat(),
            "entries_count": len(entries),
            "path": str(path),
            "filename": filename,
        }

    async def _entries(
        self,
        *,
        start: date,
        end: date,
        teacher_id: int | None = None,
        group_id: int | None = None,
    ) -> list[dict[str, Any]]:
        stmt = (
            select(ScheduleEntry)
            .join(Course)
            .where(
                ScheduleEntry.entry_date >= start,
                ScheduleEntry.entry_date <= end,
                ScheduleEntry.status == ScheduleEntryStatus.scheduled,
            )
            .options(
                selectinload(ScheduleEntry.course).selectinload(Course.teacher),
                selectinload(ScheduleEntry.course).selectinload(Course.group),
                selectinload(ScheduleEntry.room),
                selectinload(ScheduleEntry.timeslot),
            )
            .order_by(ScheduleEntry.entry_date, ScheduleEntry.timeslot_id)
        )
        if teacher_id is not None:
            stmt = stmt.where(Course.teacher_id == teacher_id)
        if group_id is not None:
            stmt = stmt.where(Course.group_id == group_id)

        rows = (await self.session.execute(stmt)).scalars().all()
        course_ids = {entry.course_id for entry in rows}
        ordered_course_entries = []
        if course_ids:
            ordered_course_entries = list(
                (
                    await self.session.execute(
                        select(ScheduleEntry)
                        .where(
                            ScheduleEntry.course_id.in_(course_ids),
                            ScheduleEntry.status == ScheduleEntryStatus.scheduled,
                        )
                        .order_by(
                            ScheduleEntry.course_id,
                            ScheduleEntry.entry_date,
                            ScheduleEntry.timeslot_id,
                            ScheduleEntry.id,
                        )
                    )
                ).scalars().all()
            )
        progress_index: dict[int, int] = {}
        counters: defaultdict[int, int] = defaultdict(int)
        for item in ordered_course_entries:
            counters[item.course_id] += 1
            progress_index[item.id] = counters[item.course_id]

        return [
            {
                "entry_date": e.entry_date.isoformat(),
                "day_of_week": e.entry_date.weekday(),
                "start_time": e.timeslot.start_time if e.timeslot else None,
                "end_time": e.timeslot.end_time if e.timeslot else None,
                "timeslot_label": e.timeslot.label if e.timeslot else "",
                "course_title": e.course.title if e.course else "",
                "teacher_name": e.course.teacher.name if e.course and e.course.teacher else "",
                "group_name": e.course.group.name if e.course and e.course.group else "",
                "room_name": e.room.name if e.room else "",
                "session_progress": (
                    f"{progress_index.get(e.id, 1)} / "
                    f"{ceil(e.course.planned_minutes / e.course.duration_minutes)}"
                ),
                "is_complete": progress_index.get(e.id, 1)
                >= ceil(e.course.planned_minutes / e.course.duration_minutes),
            }
            for e in rows
        ]

    async def _render_pdf(
        self,
        *,
        title: str,
        audience_label: str,
        audience_name: str,
        week_start: date,
        week_label: str,
        entries: list[dict[str, Any]],
        filename: str,
    ) -> Path:
        start = week_start - timedelta(days=week_start.weekday())
        include_sunday = any(entry["day_of_week"] == 6 for entry in entries)
        day_count = 7 if include_sunday else 6
        day_names = [
            "LUNDI",
            "MARDI",
            "MERCREDI",
            "JEUDI",
            "VENDREDI",
            "SAMEDI",
            "DIMANCHE",
        ]
        days = [
            {
                "index": index,
                "name": day_names[index],
                "date_label": (start + timedelta(days=index)).strftime("%d-%m-%y"),
            }
            for index in range(day_count)
        ]

        slots = list(
            (
                await self.session.execute(
                    select(TimeSlot)
                    .where(TimeSlot.day_of_week < day_count)
                    .order_by(TimeSlot.start_time, TimeSlot.end_time)
                )
            ).scalars().all()
        )
        slot_keys = sorted({(slot.start_time, slot.end_time) for slot in slots})
        by_cell: defaultdict[tuple[int, object, object], list[dict[str, Any]]] = defaultdict(list)
        for entry in entries:
            by_cell[
                (entry["day_of_week"], entry["start_time"], entry["end_time"])
            ].append(entry)

        grid_rows: list[dict[str, Any]] = []
        for index, (start_time, end_time) in enumerate(slot_keys):
            if index:
                previous_end = slot_keys[index - 1][1]
                gap_minutes = (
                    start_time.hour * 60
                    + start_time.minute
                    - previous_end.hour * 60
                    - previous_end.minute
                )
                if gap_minutes > 0:
                    grid_rows.append(
                        {
                            "kind": "pause",
                            "label": (
                                f"{previous_end.strftime('%Hh%M')} - "
                                f"{start_time.strftime('%Hh%M')}"
                            ),
                        }
                    )
            duration_minutes = (
                end_time.hour * 60
                + end_time.minute
                - start_time.hour * 60
                - start_time.minute
            )
            duration = (
                f"{duration_minutes // 60}h"
                if duration_minutes % 60 == 0
                else f"{duration_minutes // 60}h{duration_minutes % 60:02d}"
            )
            grid_rows.append(
                {
                    "kind": "slot",
                    "label": (
                        f"{start_time.strftime('%Hh%M')} - "
                        f"{end_time.strftime('%Hh%M')}"
                    ),
                    "duration": duration,
                    "cells": [
                        by_cell[(day["index"], start_time, end_time)] for day in days
                    ],
                }
            )

        template = self.env.get_template("schedule.html")
        html = template.render(
            university_name=settings.university_name,
            semester_label=settings.semester_label,
            title=title,
            audience_label=audience_label,
            audience_name=audience_name,
            week_label=week_label,
            generated_at=datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC"),
            entries_count=len(entries),
            days=days,
            rows=grid_rows,
        )
        output = EXPORTS_DIR / filename
        # WeasyPrint est sync
        from weasyprint import HTML

        HTML(string=html, base_url=str(TEMPLATES_DIR)).write_pdf(str(output))
        return output

    @staticmethod
    def _week_bounds(week_start: date | None) -> tuple[date, date, str]:
        if week_start is None:
            today = date.today()
            week_start = today - timedelta(days=today.weekday())
        monday = week_start - timedelta(days=week_start.weekday())
        sunday = monday + timedelta(days=6)
        saturday = monday + timedelta(days=5)
        months = [
            "janvier",
            "février",
            "mars",
            "avril",
            "mai",
            "juin",
            "juillet",
            "août",
            "septembre",
            "octobre",
            "novembre",
            "décembre",
        ]
        if monday.month == saturday.month:
            label = (
                f"{monday.day} au {saturday.day} "
                f"{months[saturday.month - 1]} {saturday.year}"
            )
        else:
            label = (
                f"{monday.day} {months[monday.month - 1]} au "
                f"{saturday.day} {months[saturday.month - 1]} {saturday.year}"
            )
        return monday, sunday, label
