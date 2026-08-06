"""Règles pures de chevauchement / conflits (testables sans DB)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Iterable


@dataclass(frozen=True)
class SlotWindow:
    entry_date: date
    start: time
    end: time

    @property
    def start_dt(self) -> datetime:
        return datetime.combine(self.entry_date, self.start, tzinfo=timezone.utc)

    @property
    def end_dt(self) -> datetime:
        return datetime.combine(self.entry_date, self.end, tzinfo=timezone.utc)


def times_overlap(a_start: time, a_end: time, b_start: time, b_end: time) -> bool:
    return a_start < b_end and b_start < a_end


def windows_overlap(a: SlotWindow, b: SlotWindow) -> bool:
    if a.entry_date != b.entry_date:
        return False
    return times_overlap(a.start, a.end, b.start, b.end)


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def availability_blocks(window: SlotWindow, block_start: datetime, block_end: datetime) -> bool:
    return window.start_dt < _as_utc(block_end) and _as_utc(block_start) < window.end_dt


@dataclass(frozen=True)
class Conflict:
    code: str
    message: str


@dataclass(frozen=True)
class CandidateCheck:
    teacher_id: int
    group_id: int
    room_id: int
    room_capacity: int
    student_count: int
    window: SlotWindow
    ignore_entry_id: int | None = None


@dataclass(frozen=True)
class OccupiedEntry:
    entry_id: int
    teacher_id: int
    group_id: int
    room_id: int
    window: SlotWindow
    status: str = "scheduled"


@dataclass(frozen=True)
class BlockingAvailability:
    teacher_id: int
    start_at: datetime
    end_at: datetime
    reason: str | None = None


def detect_conflicts(
    candidate: CandidateCheck,
    occupied: Iterable[OccupiedEntry],
    availabilities: Iterable[BlockingAvailability],
) -> list[Conflict]:
    conflicts: list[Conflict] = []

    if candidate.student_count and candidate.room_capacity < candidate.student_count:
        conflicts.append(
            Conflict(
                code="room_capacity",
                message=(
                    f"Salle trop petite (capacité {candidate.room_capacity} "
                    f"< {candidate.student_count} étudiants)."
                ),
            )
        )

    for entry in occupied:
        if candidate.ignore_entry_id is not None and entry.entry_id == candidate.ignore_entry_id:
            continue
        if entry.status != "scheduled":
            continue
        if not windows_overlap(candidate.window, entry.window):
            continue

        if entry.teacher_id == candidate.teacher_id:
            conflicts.append(
                Conflict(
                    code="teacher_busy",
                    message=f"Enseignant déjà occupé (séance #{entry.entry_id}).",
                )
            )
        if entry.room_id == candidate.room_id:
            conflicts.append(
                Conflict(
                    code="room_busy",
                    message=f"Salle déjà prise (séance #{entry.entry_id}).",
                )
            )
        if entry.group_id == candidate.group_id:
            conflicts.append(
                Conflict(
                    code="group_busy",
                    message=f"Groupe déjà en cours (séance #{entry.entry_id}).",
                )
            )

    for block in availabilities:
        if block.teacher_id != candidate.teacher_id:
            continue
        if availability_blocks(candidate.window, block.start_at, block.end_at):
            reason = block.reason or "indisponibilité"
            conflicts.append(
                Conflict(
                    code="teacher_unavailable",
                    message=f"Enseignant indisponible ({reason}).",
                )
            )

    return conflicts
