"""Construction des outils LangChain liés à une session DB."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from langchain_core.tools import tool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Room, Teacher
from app.services.history_service import HistoryService
from app.tools import planning as planning_tools


def _dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def build_planning_tools(session: AsyncSession) -> list[Callable[..., Any]]:
    @tool
    async def list_teachers() -> str:
        """Liste les enseignants (id, nom, email, téléphone WhatsApp)."""
        rows = (await session.execute(select(Teacher).order_by(Teacher.id))).scalars().all()
        return _dump(
            {
                "ok": True,
                "teachers": [
                    {
                        "id": t.id,
                        "name": t.name,
                        "email": t.email,
                        "phone_whatsapp": t.phone_whatsapp,
                    }
                    for t in rows
                ],
            }
        )

    @tool
    async def list_rooms() -> str:
        """Liste les salles disponibles (id, nom, capacité)."""
        rows = (await session.execute(select(Room).order_by(Room.id))).scalars().all()
        return _dump(
            {
                "ok": True,
                "rooms": [
                    {"id": r.id, "name": r.name, "capacity": r.capacity}
                    for r in rows
                ],
                "count": len(rows),
            }
        )

    @tool
    async def list_courses() -> str:
        """Liste les cours avec prof, durée séance, volume prévu, heures faites et heures restantes (format H)."""
        return _dump(await planning_tools.list_courses(session))

    @tool
    async def list_schedule(
        day: str | None = None,
        period: str | None = None,
        week_start: str | None = None,
    ) -> str:
        """Planning des séances.
        - day: une date AAAA-MM-JJ
        - period: 'current_week' (semaine en cours) ou 'next_week' (semaine prochaine)
        - week_start: lundi (ou n'importe quel jour) d'une semaine au format AAAA-MM-JJ
        """
        return _dump(
            await planning_tools.list_schedule(
                session, day=day, week_start=week_start, period=period
            )
        )

    @tool
    async def get_teacher(teacher_id: int) -> str:
        """Récupère un enseignant par son identifiant numérique."""
        return _dump(await planning_tools.get_teacher(session, teacher_id))

    @tool
    async def get_teacher_schedule(teacher_id: int, day: str | None = None) -> str:
        """Planning d'un enseignant. day optionnel au format AAAA-MM-JJ."""
        return _dump(await planning_tools.get_teacher_schedule(session, teacher_id, day))

    @tool
    async def get_teacher_availability(teacher_id: int) -> str:
        """Indisponibilités enregistrées pour un enseignant."""
        return _dump(await planning_tools.get_teacher_availability(session, teacher_id))

    @tool
    async def update_teacher_availability(
        teacher_id: int,
        start_at: str,
        end_at: str,
        reason: str | None = None,
    ) -> str:
        """Enregistre une indisponibilité. start_at/end_at en ISO-8601."""
        return _dump(
            await planning_tools.update_teacher_availability(
                session, teacher_id, start_at, end_at, reason
            )
        )

    @tool
    async def find_impacted_entries(teacher_id: int, day: str) -> str:
        """Séances impactées pour un enseignant à une date AAAA-MM-JJ."""
        return _dump(await planning_tools.find_impacted_entries(session, teacher_id, day))

    @tool
    async def find_available_slots(
        entry_id: int,
        search_start: str,
        search_end: str,
        limit: int = 3,
    ) -> str:
        """Cherche des créneaux de report sans conflit pour une séance."""
        return _dump(
            await planning_tools.find_available_slots(
                session, entry_id, search_start, search_end, limit
            )
        )

    @tool
    async def detect_conflicts(
        entry_id: int,
        entry_date: str,
        timeslot_id: int,
        room_id: int,
    ) -> str:
        """Vérifie les conflits d'un déplacement envisagé."""
        return _dump(
            await planning_tools.detect_conflicts(
                session, entry_id, entry_date, timeslot_id, room_id
            )
        )

    @tool
    async def propose_move_course(
        entry_id: int,
        entry_date: str,
        timeslot_id: int,
        room_id: int,
        proposed_by: str = "agent",
    ) -> str:
        """Crée une proposition de déplacement (statut proposed), sans l'appliquer."""
        return _dump(
            await planning_tools.propose_move_course(
                session, entry_id, entry_date, timeslot_id, room_id, proposed_by
            )
        )

    @tool
    async def apply_schedule_change(change_id: int) -> str:
        """Applique un changement UNIQUEMENT après confirmation explicite de l'utilisateur."""
        return _dump(await planning_tools.apply_schedule_change(session, change_id))

    @tool
    async def confirm_presence(entry_id: int, teacher_id: int | None = None) -> str:
        """Confirme la présence du professeur pour une séance (réponse au rappel J-n)."""
        return _dump(
            await planning_tools.confirm_presence(session, entry_id, teacher_id)
        )

    @tool
    async def cancel_course(
        entry_id: int,
        reason: str | None = None,
        teacher_id: int | None = None,
        propose_alternatives: bool = True,
    ) -> str:
        """Annule une séance et propose éventuellement d'autres créneaux de report."""
        return _dump(
            await planning_tools.cancel_course(
                session,
                entry_id=entry_id,
                reason=reason,
                teacher_id=teacher_id,
                propose_alternatives=propose_alternatives,
            )
        )

    @tool
    async def get_teacher_actions_history(
        kind: str = "all",
        limit: int = 50,
    ) -> str:
        """Historique admin des actions enseignants.
        kind: all | confirmations | reschedules | reminders
        """
        return _dump(
            await HistoryService(session).teacher_actions(kind=kind, limit=limit)
        )

    @tool
    async def generate_teacher_schedule_pdf(
        teacher_id: int, week_start: str | None = None
    ) -> str:
        """Génère le PDF d'emploi du temps d'un enseignant (week_start optionnel AAAA-MM-JJ)."""
        return _dump(
            await planning_tools.generate_teacher_schedule_pdf(
                session, teacher_id, week_start
            )
        )

    @tool
    async def generate_group_schedule_pdf(
        group_id: int, week_start: str | None = None
    ) -> str:
        """Génère le PDF d'emploi du temps d'un groupe (week_start optionnel AAAA-MM-JJ)."""
        return _dump(
            await planning_tools.generate_group_schedule_pdf(
                session, group_id, week_start
            )
        )

    return [
        list_teachers,
        list_rooms,
        list_courses,
        list_schedule,
        get_teacher,
        get_teacher_schedule,
        get_teacher_availability,
        update_teacher_availability,
        find_impacted_entries,
        find_available_slots,
        detect_conflicts,
        propose_move_course,
        apply_schedule_change,
        confirm_presence,
        cancel_course,
        get_teacher_actions_history,
        generate_teacher_schedule_pdf,
        generate_group_schedule_pdf,
    ]
