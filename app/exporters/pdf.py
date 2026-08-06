"""Export PDF des emplois du temps (Jinja2 + WeasyPrint)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.domain.models import Course, ScheduleEntry, ScheduleEntryStatus, StudentGroup, Teacher

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
        return [
            {
                "entry_date": e.entry_date.isoformat(),
                "timeslot_label": e.timeslot.label if e.timeslot else "",
                "course_title": e.course.title if e.course else "",
                "teacher_name": e.course.teacher.name if e.course and e.course.teacher else "",
                "group_name": e.course.group.name if e.course and e.course.group else "",
                "room_name": e.room.name if e.room else "",
            }
            for e in rows
        ]

    async def _render_pdf(
        self,
        *,
        title: str,
        week_label: str,
        entries: list[dict[str, Any]],
        filename: str,
    ) -> Path:
        template = self.env.get_template("schedule.html")
        html = template.render(
            university_name=settings.university_name,
            semester_label=settings.semester_label,
            title=title,
            week_label=week_label,
            generated_at=datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC"),
            entries=entries,
        )
        output = EXPORTS_DIR / filename
        # WeasyPrint est sync
        from weasyprint import HTML

        HTML(string=html, base_url=str(TEMPLATES_DIR)).write_pdf(str(output))
        return output

    @staticmethod
    def _week_bounds(week_start: date | None) -> tuple[date, date, str]:
        if week_start is None:
            # Semaine de démo seed par défaut
            week_start = date(2026, 8, 3)
        monday = week_start - timedelta(days=week_start.weekday())
        sunday = monday + timedelta(days=6)
        label = f"{monday.isoformat()} au {sunday.isoformat()}"
        return monday, sunday, label
