"""Export PDF des emplois du temps (Jinja2 + WeasyPrint).

Format institutionnel : EDT_S{semestre}_SEMAINE{n}_{NIVEAU}_{PARCOURS}.pdf
ex. EDT_S2_SEMAINE8_B3_ASI.pdf
"""

from __future__ import annotations

import re
import unicodedata
import zipfile
from collections import defaultdict
from datetime import date, timedelta
from math import ceil
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.domain.models import (
    AcademicLevel,
    Course,
    ScheduleEntry,
    ScheduleEntryStatus,
    StudentGroup,
    Teacher,
    TimeSlot,
)

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
EXPORTS_DIR = Path(__file__).resolve().parents[2] / "exports"

_MONTHS_SHORT = [
    "jan",
    "fév",
    "mar",
    "avr",
    "mai",
    "juin",
    "juil",
    "août",
    "sept",
    "oct",
    "nov",
    "déc",
]
_MONTHS_LONG = [
    "Janvier",
    "Février",
    "Mars",
    "Avril",
    "Mai",
    "Juin",
    "Juillet",
    "Août",
    "Septembre",
    "Octobre",
    "Novembre",
    "Décembre",
]


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", ascii_text).strip("_")
    return cleaned.upper()


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

        start, end, week_label, week_number = self._week_bounds(week_start)
        entries = await self._entries(
            start=start,
            end=end,
            teacher_id=teacher_id,
        )
        semester = self._resolve_semester(entries)
        filename = self._edt_filename(
            semester=semester,
            week_number=week_number,
            parts=["ENS", _slug(teacher.name) or f"T{teacher_id}"],
        )
        path = await self._render_pdf(
            title=f"Emploi de temps — {teacher.name}",
            audience_name=teacher.name.upper(),
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
            "media_type": "application/pdf",
        }

    async def generate_group_schedule_pdf(
        self,
        group_id: int,
        week_start: date | None = None,
    ) -> dict[str, Any]:
        group = await self._load_group(group_id)
        if group is None:
            raise ValueError(f"Groupe #{group_id} introuvable")

        start, end, week_label, week_number = self._week_bounds(week_start)
        entries = await self._entries(start=start, end=end, group_id=group_id)
        semester = self._resolve_semester(entries)
        filename = self._edt_filename(
            semester=semester,
            week_number=week_number,
            parts=self._group_filename_parts(group),
        )
        path = await self._render_pdf(
            title=f"Emploi de temps — {group.name}",
            audience_name=self._group_audience_label(group),
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
            "media_type": "application/pdf",
        }

    async def generate_level_schedule_pdf(
        self,
        level_id: int | None = None,
        *,
        level_code: str | None = None,
        week_start: date | None = None,
    ) -> dict[str, Any]:
        """PDF unique pour un parcours (academic level) — format institutionnel."""
        level = await self._load_level(level_id=level_id, level_code=level_code)
        if level is None:
            raise ValueError("Parcours introuvable (level_id / level_code)")

        start, end, week_label, week_number = self._week_bounds(week_start)
        entries = await self._entries(start=start, end=end, level_id=level.id)
        semester = self._resolve_semester(entries)
        filename = self._edt_filename(
            semester=semester,
            week_number=week_number,
            parts=self._level_filename_parts(level),
        )
        path = await self._render_pdf(
            title=f"Emploi de temps — {level.label}",
            audience_name=self._level_audience_label(level),
            week_start=start,
            week_label=week_label,
            entries=entries,
            filename=filename,
        )
        return {
            "ok": True,
            "type": "level",
            "level_id": level.id,
            "level_code": level.code,
            "level_label": level.label,
            "week_start": start.isoformat(),
            "week_end": end.isoformat(),
            "entries_count": len(entries),
            "path": str(path),
            "filename": filename,
            "media_type": "application/pdf",
        }

    async def generate_week_schedule_pdf(
        self,
        week_start: date | None = None,
        *,
        preview: bool = False,
    ) -> dict[str, Any]:
        """Exporte le format institutionnel : un PDF par groupe (ZIP si plusieurs).

        En mode preview, retourne toujours un seul PDF (premier groupe concerné).
        """
        start, end, week_label, week_number = self._week_bounds(week_start)
        group_ids = list(
            (
                await self.session.execute(
                    select(Course.group_id)
                    .join(ScheduleEntry, ScheduleEntry.course_id == Course.id)
                    .where(
                        ScheduleEntry.entry_date >= start,
                        ScheduleEntry.entry_date <= end,
                        ScheduleEntry.status == ScheduleEntryStatus.scheduled,
                    )
                    .distinct()
                    .order_by(Course.group_id)
                )
            ).scalars().all()
        )

        if not group_ids:
            semester = settings.semester_number
            filename = self._edt_filename(
                semester=semester,
                week_number=week_number,
                parts=["TOUS"],
            )
            path = await self._render_pdf(
                title=f"Emploi de temps — Semaine {week_label}",
                audience_name="TOUS LES GROUPES",
                week_start=start,
                week_label=week_label,
                entries=[],
                filename=filename,
            )
            return {
                "ok": True,
                "type": "week",
                "week_start": start.isoformat(),
                "week_end": end.isoformat(),
                "entries_count": 0,
                "path": str(path),
                "filename": filename,
                "media_type": "application/pdf",
                "files": [filename],
            }

        if preview or len(group_ids) == 1:
            result = await self.generate_group_schedule_pdf(
                group_ids[0], week_start=start
            )
            result["type"] = "week"
            result["preview"] = preview
            return result

        pdf_results: list[dict[str, Any]] = []
        for group_id in group_ids:
            pdf_results.append(
                await self.generate_group_schedule_pdf(group_id, week_start=start)
            )

        semester = max(
            (self._semester_from_filename(item["filename"]) for item in pdf_results),
            default=settings.semester_number,
        )
        zip_name = self._edt_filename(
            semester=semester,
            week_number=week_number,
            parts=["GROUPES"],
            extension="zip",
        )
        zip_path = EXPORTS_DIR / zip_name
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for item in pdf_results:
                archive.write(item["path"], arcname=item["filename"])

        return {
            "ok": True,
            "type": "week",
            "week_start": start.isoformat(),
            "week_end": end.isoformat(),
            "entries_count": sum(item["entries_count"] for item in pdf_results),
            "path": str(zip_path),
            "filename": zip_name,
            "media_type": "application/zip",
            "files": [item["filename"] for item in pdf_results],
        }

    async def _load_group(self, group_id: int) -> StudentGroup | None:
        return (
            await self.session.execute(
                select(StudentGroup)
                .where(StudentGroup.id == group_id)
                .options(selectinload(StudentGroup.academic_level))
            )
        ).scalar_one_or_none()

    async def _load_level(
        self,
        *,
        level_id: int | None = None,
        level_code: str | None = None,
    ) -> AcademicLevel | None:
        if level_id is not None:
            return await self.session.get(AcademicLevel, level_id)
        if level_code:
            code = level_code.strip()
            return (
                await self.session.execute(
                    select(AcademicLevel).where(AcademicLevel.code.ilike(code))
                )
            ).scalar_one_or_none()
        return None

    async def _entries(
        self,
        *,
        start: date,
        end: date,
        teacher_id: int | None = None,
        group_id: int | None = None,
        level_id: int | None = None,
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
                selectinload(ScheduleEntry.course)
                .selectinload(Course.group)
                .selectinload(StudentGroup.academic_level),
                selectinload(ScheduleEntry.room),
                selectinload(ScheduleEntry.timeslot),
            )
            .order_by(ScheduleEntry.entry_date, ScheduleEntry.timeslot_id)
        )
        if teacher_id is not None:
            stmt = stmt.where(Course.teacher_id == teacher_id)
        if group_id is not None:
            stmt = stmt.where(Course.group_id == group_id)
        if level_id is not None:
            stmt = stmt.join(StudentGroup, Course.group_id == StudentGroup.id).where(
                StudentGroup.academic_level_id == level_id
            )

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
                "semester": e.course.semester if e.course else settings.semester_number,
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
                "date_label": self._day_header_date(start + timedelta(days=index)),
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
            title=title,
            audience_name=audience_name,
            week_label=week_label,
            director_name=settings.pdf_director_name,
            days=days,
            rows=grid_rows,
        )
        output = EXPORTS_DIR / filename
        from weasyprint import HTML

        HTML(string=html, base_url=str(TEMPLATES_DIR)).write_pdf(str(output))
        return output

    @staticmethod
    def _day_header_date(value: date) -> str:
        return f"{value.day:02d}-{_MONTHS_SHORT[value.month - 1]}-{str(value.year)[-2:]}"

    @staticmethod
    def _week_bounds(week_start: date | None) -> tuple[date, date, str, int]:
        if week_start is None:
            today = date.today()
            week_start = today - timedelta(days=today.weekday())
        monday = week_start - timedelta(days=week_start.weekday())
        sunday = monday + timedelta(days=6)
        saturday = monday + timedelta(days=5)
        if monday.month == saturday.month:
            label = (
                f"{monday.day} au {saturday.day} "
                f"{_MONTHS_LONG[saturday.month - 1]} {saturday.year}"
            )
        else:
            label = (
                f"{monday.day} {_MONTHS_LONG[monday.month - 1]} au "
                f"{saturday.day} {_MONTHS_LONG[saturday.month - 1]} {saturday.year}"
            )
        week_number = PdfExporter._academic_week_number(monday)
        return monday, sunday, label, week_number

    @staticmethod
    def _academic_week_number(monday: date) -> int:
        semester_start = settings.semester_start_date
        if semester_start is None:
            return monday.isocalendar().week
        start_monday = semester_start - timedelta(days=semester_start.weekday())
        weeks = ((monday - start_monday).days // 7) + 1
        return max(1, weeks)

    @staticmethod
    def _resolve_semester(entries: list[dict[str, Any]]) -> int:
        values = [int(item["semester"]) for item in entries if item.get("semester")]
        if values:
            return max(set(values), key=values.count)
        return settings.semester_number

    @staticmethod
    def _edt_filename(
        *,
        semester: int,
        week_number: int,
        parts: list[str],
        extension: str = "pdf",
    ) -> str:
        suffix = "_".join(part for part in parts if part)
        base = f"EDT_S{semester}_SEMAINE{week_number}"
        if suffix:
            return f"{base}_{suffix}.{extension}"
        return f"{base}.{extension}"

    @staticmethod
    def _semester_from_filename(filename: str) -> int:
        match = re.search(r"EDT_S(\d+)_", filename)
        return int(match.group(1)) if match else settings.semester_number

    @staticmethod
    def _level_filename_parts(level: AcademicLevel) -> list[str]:
        code = _slug(level.code) if level.code else ""
        specialty = _slug(level.speciality or "")
        parts = [part for part in (code, specialty) if part]
        return parts or [_slug(level.label) or f"L{level.id}"]

    @staticmethod
    def _level_audience_label(level: AcademicLevel) -> str:
        specialty = (level.speciality or "").strip()
        label = (level.label or "").strip()
        code = (level.code or "").strip()
        if label and code:
            head = f"{label} ({code})"
        else:
            head = label or code or f"Parcours #{level.id}"
        if specialty and specialty.upper() not in head.upper():
            return f"{head} {specialty}".strip().upper()
        return head.upper()

    @staticmethod
    def _group_filename_parts(group: StudentGroup) -> list[str]:
        level: AcademicLevel | None = group.academic_level
        code = _slug(level.code) if level and level.code else ""
        specialty_source = ""
        if level and level.speciality:
            specialty_source = level.speciality
        else:
            specialty_source = group.name
            if code and specialty_source.upper().startswith(code):
                specialty_source = specialty_source[len(code) :].strip(" -_")
        specialty = _slug(specialty_source)
        parts = [part for part in (code, specialty) if part]
        return parts or [_slug(group.name) or f"G{group.id}"]

    @staticmethod
    def _group_audience_label(group: StudentGroup) -> str:
        level = group.academic_level
        if level is None:
            return group.name.upper()
        specialty = (level.speciality or "").strip()
        if not specialty:
            specialty = group.name
            code = (level.code or "").strip()
            if code and specialty.upper().startswith(code.upper()):
                specialty = specialty[len(code) :].strip(" -_")
        label = (level.label or "").strip()
        code = (level.code or "").strip()
        if label and code:
            head = f"{label} ({code})"
        else:
            head = label or code or group.name
        if specialty and specialty.upper() not in head.upper():
            return f"{head} {specialty}".strip().upper()
        return head.upper()
