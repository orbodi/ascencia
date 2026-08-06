"""Historique admin : confirmations de présence et reports."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import AuditLog, Teacher

CONFIRM_ACTIONS = {"presence_confirmed"}
RESCHEDULE_ACTIONS = {
    "course_cancelled",
    "propose_move_course",
    "apply_schedule_change",
}
REMINDER_ACTIONS = {"presence_reminder_sent"}


class HistoryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def teacher_actions(
        self,
        *,
        kind: str = "all",
        limit: int = 50,
    ) -> dict[str, Any]:
        actions = self._actions_for_kind(kind)
        result = await self.session.execute(
            select(AuditLog)
            .where(AuditLog.action.in_(actions))
            .order_by(AuditLog.id.desc())
            .limit(limit)
        )
        rows = result.scalars().all()
        teacher_ids = {
            int(r.payload["teacher_id"])
            for r in rows
            if isinstance(r.payload, dict) and r.payload.get("teacher_id") is not None
        }
        teachers = {}
        if teacher_ids:
            t_result = await self.session.execute(
                select(Teacher).where(Teacher.id.in_(teacher_ids))
            )
            teachers = {t.id: t for t in t_result.scalars().all()}

        items = [self._serialize(row, teachers) for row in rows]
        return {
            "ok": True,
            "kind": kind,
            "count": len(items),
            "items": items,
            "summary": {
                "confirmations": sum(1 for i in items if i["category"] == "confirmation"),
                "reschedules": sum(1 for i in items if i["category"] == "reschedule"),
                "reminders": sum(1 for i in items if i["category"] == "reminder"),
            },
        }

    @staticmethod
    def _actions_for_kind(kind: str) -> set[str]:
        if kind == "confirmations":
            return CONFIRM_ACTIONS
        if kind == "reschedules":
            return RESCHEDULE_ACTIONS
        if kind == "reminders":
            return REMINDER_ACTIONS
        return CONFIRM_ACTIONS | RESCHEDULE_ACTIONS | REMINDER_ACTIONS

    @staticmethod
    def _category(action: str) -> str:
        if action in CONFIRM_ACTIONS:
            return "confirmation"
        if action in RESCHEDULE_ACTIONS:
            return "reschedule"
        if action in REMINDER_ACTIONS:
            return "reminder"
        return "other"

    @staticmethod
    def _serialize(row: AuditLog, teachers: dict[int, Teacher]) -> dict[str, Any]:
        payload = row.payload or {}
        teacher_id = payload.get("teacher_id")
        teacher = teachers.get(int(teacher_id)) if teacher_id is not None else None
        return {
            "id": row.id,
            "action": row.action,
            "category": HistoryService._category(row.action),
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "teacher_id": teacher_id,
            "teacher_name": teacher.name if teacher else None,
            "entry_id": payload.get("entry_id"),
            "entry_date": payload.get("entry_date")
            or (payload.get("after") or {}).get("entry_date"),
            "course_title": payload.get("course_title")
            or (payload.get("before") or {}).get("course_title"),
            "reason": payload.get("reason"),
            "payload": payload,
        }
