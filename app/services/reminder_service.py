"""Rappels de confirmation de présence aux enseignants."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.domain.models import AuditLog, Course, ScheduleEntry, ScheduleEntryStatus
from app.services.system_config import get_agent_name
from app.whatsapp import WhatsAppClient


class ReminderService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.whatsapp = WhatsAppClient()

    async def send_presence_confirmations(
        self,
        *,
        days_ahead: int | None = None,
        on_date: date | None = None,
    ) -> dict[str, Any]:
        target = on_date or (
            date.today() + timedelta(days=days_ahead or settings.reminder_days_ahead)
        )

        result = await self.session.execute(
            select(ScheduleEntry)
            .where(
                ScheduleEntry.entry_date == target,
                ScheduleEntry.status == ScheduleEntryStatus.scheduled,
            )
            .options(
                selectinload(ScheduleEntry.course).selectinload(Course.teacher),
                selectinload(ScheduleEntry.course).selectinload(Course.group),
                selectinload(ScheduleEntry.timeslot),
                selectinload(ScheduleEntry.room),
            )
        )
        entries = result.scalars().all()
        sent: list[dict[str, Any]] = []
        agent_name = await get_agent_name(self.session)

        for entry in entries:
            teacher = entry.course.teacher
            phone = teacher.phone_whatsapp or f"teacher-{teacher.id}"
            slot = entry.timeslot.label if entry.timeslot else "?"
            message = (
                f"Bonjour {teacher.name},\n"
                f"Confirmation de présence demandée pour le cours "
                f"« {entry.course.title} » le {entry.entry_date.isoformat()} "
                f"({slot}, salle {entry.room.name if entry.room else '?'}, "
                f"groupe {entry.course.group.name if entry.course.group else '?'}).\n\n"
                f"Répondez à l'assistant {agent_name} :\n"
                f"- « Je confirme la séance #{entry.id} »\n"
                f"- ou « J'annule la séance #{entry.id} » pour proposer un report.\n"
                f"(Réf. entry_id={entry.id}, teacher_id={teacher.id})"
            )
            delivery = await self.whatsapp.send_text(phone, message)
            self.session.add(
                AuditLog(
                    action="presence_reminder_sent",
                    payload={
                        "entry_id": entry.id,
                        "teacher_id": teacher.id,
                        "entry_date": entry.entry_date.isoformat(),
                        "to": phone,
                        "mock": delivery.get("mock", False),
                    },
                )
            )
            sent.append(
                {
                    "entry_id": entry.id,
                    "teacher_id": teacher.id,
                    "teacher_name": teacher.name,
                    "course_title": entry.course.title,
                    "entry_date": entry.entry_date.isoformat(),
                    "to": phone,
                    "message": message,
                    "delivery": delivery,
                }
            )

        await self.session.commit()
        return {
            "ok": True,
            "target_date": target.isoformat(),
            "days_ahead": days_ahead
            if on_date is None
            else (target - date.today()).days,
            "sent_count": len(sent),
            "reminders": sent,
        }
