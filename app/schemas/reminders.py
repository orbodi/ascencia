from datetime import date

from pydantic import BaseModel, Field


class ReminderSendRequest(BaseModel):
    days_ahead: int | None = Field(
        default=None,
        description="Nombre de jours avant le cours (défaut: REMINDER_DAYS_AHEAD / 3).",
    )
    on_date: date | None = Field(
        default=None,
        description="Date cible forcée (ex: 2026-08-03 pour la démo).",
    )


class ReminderSendResponse(BaseModel):
    ok: bool
    target_date: str
    days_ahead: int
    sent_count: int
    reminders: list[dict]
