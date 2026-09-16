"""Calendrier académique (numéro de semaine depuis le début de semestre)."""

from __future__ import annotations

from datetime import date, timedelta

from app.config import settings


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def academic_week_number(
    week_start: date, *, semester_start: date | None = None
) -> int:
    """Semaine académique 1 = lundi de semester_start (ou ISO si absent)."""
    monday = monday_of(week_start)
    start = (
        semester_start
        if semester_start is not None
        else settings.semester_start_date
    )
    if start is None:
        return monday.isocalendar().week
    start_monday = monday_of(start)
    weeks = ((monday - start_monday).days // 7) + 1
    return max(1, weeks)
