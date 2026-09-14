"""Construction des outils LangChain liés à une session DB."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from typing import Any

from langchain_core.tools import tool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.models import (
    AcademicLevel,
    Course,
    Room,
    ScheduleChange,
    ScheduleEntry,
    StudentGroup,
    Teacher,
)
from app.services.availability_outreach import AvailabilityOutreachService
from app.services.autonomous_workflow import AutonomousWorkflowService
from app.services.history_service import HistoryService
from app.services.generation_service import ScheduleGenerationService
from app.services.planning_cycle import PlanningCycleService
from app.tools import planning as planning_tools
from app.whatsapp import WhatsAppClient


def _dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def build_planning_tools(
    session: AsyncSession,
    *,
    actor_role: str = "admin",
    actor_teacher_id: int | None = None,
    whatsapp_to: str | None = None,
) -> list[Callable[..., Any]]:
    def teacher_scope_error(requested_teacher_id: int) -> str | None:
        if actor_role == "teacher" and requested_teacher_id != actor_teacher_id:
            return _dump({"ok": False, "error": "Accès limité à votre propre fiche"})
        return None

    async def deliver_pdf_if_whatsapp(result: dict[str, Any]) -> dict[str, Any]:
        """Sur canal WhatsApp, joint le PDF généré au fil de discussion."""
        if not whatsapp_to or not result.get("ok") or not result.get("path"):
            return result
        delivery = await WhatsAppClient().send_document(
            whatsapp_to,
            result["path"],
            caption=(
                f"Emploi du temps — "
                f"{result.get('level_label') or result.get('teacher_name') or result.get('group_name') or 'planning'}"
            ),
            filename=result.get("filename"),
        )
        result = {**result, "whatsapp_delivery": delivery}
        if delivery.get("ok"):
            result["delivered_on_whatsapp"] = True
            result["user_message"] = (
                "Le fichier PDF a été envoyé en pièce jointe sur WhatsApp. "
                "Ne renvoie pas le chemin serveur ; confirme simplement l'envoi."
            )
        else:
            result["delivered_on_whatsapp"] = False
            result["user_message"] = (
                "Le PDF a été généré mais l'envoi WhatsApp a échoué : "
                f"{delivery.get('error') or 'erreur inconnue'}."
            )
        return result

    async def change_scope_error(change_id: int) -> str | None:
        if actor_role != "teacher":
            return None
        change = await session.get(ScheduleChange, change_id)
        if change is None:
            return _dump({"ok": False, "error": "Proposition introuvable"})
        teacher_id = await session.scalar(
            select(Course.teacher_id)
            .join(ScheduleEntry, ScheduleEntry.course_id == Course.id)
            .where(ScheduleEntry.id == change.entry_id)
        )
        if teacher_id != actor_teacher_id:
            return _dump({"ok": False, "error": "Accès limité à vos propres séances"})
        return None
    @tool
    async def list_levels() -> str:
        """Liste les parcours / niveaux académiques (id, code, label, spécialité)."""
        rows = (
            await session.execute(select(AcademicLevel).order_by(AcademicLevel.id))
        ).scalars().all()
        return _dump(
            {
                "ok": True,
                "levels": [
                    {
                        "id": level.id,
                        "code": level.code,
                        "label": level.label,
                        "degree": level.degree,
                        "year": level.year,
                        "speciality": level.speciality,
                    }
                    for level in rows
                ],
            }
        )

    @tool
    async def list_groups() -> str:
        """Liste les groupes étudiants avec leur parcours (academic_level_id)."""
        rows = (
            await session.execute(
                select(StudentGroup)
                .options(selectinload(StudentGroup.academic_level))
                .order_by(StudentGroup.id)
            )
        ).scalars().all()
        return _dump(
            {
                "ok": True,
                "groups": [
                    {
                        "id": group.id,
                        "name": group.name,
                        "academic_level_id": group.academic_level_id,
                        "level_code": group.academic_level.code
                        if group.academic_level
                        else None,
                        "level_label": group.academic_level.label
                        if group.academic_level
                        else None,
                    }
                    for group in rows
                ],
            }
        )

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
        if error := teacher_scope_error(teacher_id):
            return error
        return _dump(await planning_tools.get_teacher(session, teacher_id))

    @tool
    async def get_teacher_schedule(teacher_id: int, day: str | None = None) -> str:
        """Planning d'un enseignant. day optionnel au format AAAA-MM-JJ."""
        if error := teacher_scope_error(teacher_id):
            return error
        return _dump(await planning_tools.get_teacher_schedule(session, teacher_id, day))

    @tool
    async def get_teacher_availability(teacher_id: int) -> str:
        """Indisponibilités enregistrées pour un enseignant."""
        if error := teacher_scope_error(teacher_id):
            return error
        return _dump(await planning_tools.get_teacher_availability(session, teacher_id))

    @tool
    async def update_teacher_availability(
        teacher_id: int,
        start_at: str,
        end_at: str,
        reason: str | None = None,
    ) -> str:
        """Enregistre une indisponibilité. start_at/end_at en ISO-8601."""
        if error := teacher_scope_error(teacher_id):
            return error
        return _dump(
            await planning_tools.update_teacher_availability(
                session, teacher_id, start_at, end_at, reason
            )
        )

    @tool
    async def find_impacted_entries(teacher_id: int, day: str) -> str:
        """Séances impactées pour un enseignant à une date AAAA-MM-JJ."""
        if error := teacher_scope_error(teacher_id):
            return error
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
        if actor_role == "teacher":
            teacher_id = await session.scalar(
                select(Course.teacher_id)
                .join(ScheduleEntry, ScheduleEntry.course_id == Course.id)
                .where(ScheduleEntry.id == entry_id)
            )
            if teacher_id != actor_teacher_id:
                return _dump({"ok": False, "error": "Accès limité à vos propres séances"})
        return _dump(
            await planning_tools.propose_move_course(
                session, entry_id, entry_date, timeslot_id, room_id, proposed_by
            )
        )

    @tool
    async def approve_schedule_change(change_id: int) -> str:
        """Approuve une proposition après confirmation explicite.

        Un enseignant ne peut approuver qu'un changement concernant son propre cours.
        """
        if error := await change_scope_error(change_id):
            return error
        approved_by = (
            f"teacher:{actor_teacher_id}" if actor_role == "teacher" else "admin-agent"
        )
        return _dump(
            await planning_tools.approve_schedule_change(
                session, change_id, approved_by=approved_by
            )
        )

    @tool
    async def apply_schedule_change(change_id: int) -> str:
        """Applique un changement UNIQUEMENT après confirmation explicite de l'utilisateur."""
        if error := await change_scope_error(change_id):
            return error
        return _dump(await planning_tools.apply_schedule_change(session, change_id))

    @tool
    async def confirm_presence(entry_id: int, teacher_id: int | None = None) -> str:
        """Confirme la présence du professeur pour une séance (réponse au rappel J-n)."""
        if actor_role == "teacher" and teacher_id != actor_teacher_id:
            return _dump({"ok": False, "error": "teacher_id de session requis"})
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
        if actor_role == "teacher" and teacher_id != actor_teacher_id:
            return _dump({"ok": False, "error": "teacher_id de session requis"})
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
    async def generate_parcours_schedule_pdf(
        level_id: int | None = None,
        level_code: str | None = None,
        week_start: str | None = None,
    ) -> str:
        """Génère UN seul PDF d'emploi du temps pour un parcours (niveau académique).
        Préférez cet outil par défaut quand on demande « le planning » / « l'EDT ».
        Identifiez le parcours via list_levels (level_id ou level_code, ex. B3, L3-INFO).
        Sur WhatsApp, le fichier est envoyé en pièce jointe.
        """
        if level_id is None and not (level_code or "").strip():
            return _dump(
                {
                    "ok": False,
                    "error": "Indiquez level_id ou level_code (utilisez list_levels).",
                }
            )
        result = await planning_tools.generate_level_schedule_pdf(
            session,
            level_id=level_id,
            level_code=level_code,
            week_start=week_start,
        )
        return _dump(await deliver_pdf_if_whatsapp(result))

    @tool
    async def generate_teacher_schedule_pdf(
        teacher_id: int, week_start: str | None = None
    ) -> str:
        """Génère le PDF d'un enseignant uniquement si l'utilisateur le demande explicitement.
        Pour un planning de parcours / promotion, utilisez generate_parcours_schedule_pdf.
        """
        if error := teacher_scope_error(teacher_id):
            return error
        result = await planning_tools.generate_teacher_schedule_pdf(
            session, teacher_id, week_start
        )
        return _dump(await deliver_pdf_if_whatsapp(result))

    @tool
    async def generate_group_schedule_pdf(
        group_id: int, week_start: str | None = None
    ) -> str:
        """Génère le PDF d'un groupe précis. Préférez generate_parcours_schedule_pdf
        pour un parcours complet en un seul fichier.
        """
        result = await planning_tools.generate_group_schedule_pdf(
            session, group_id, week_start
        )
        return _dump(await deliver_pdf_if_whatsapp(result))

    @tool
    async def preview_availability_form_delivery(
        teacher_id: int | None = None,
        channel: str = "both",
    ) -> str:
        """Prévisualise l'envoi du formulaire de disponibilités (1 prof ou tous).
        teacher_id omis = tous les enseignants actifs.
        """
        if actor_role != "admin":
            return _dump({"ok": False, "error": "Action réservée à l'administration"})
        if channel not in {"email", "whatsapp", "both"}:
            return _dump({"ok": False, "error": "Canal invalide"})
        return _dump(
            await AvailabilityOutreachService(session).preview(
                teacher_id=teacher_id,
                channel=channel,  # type: ignore[arg-type]
            )
        )

    @tool
    async def send_availability_form(
        channel: str,
        approved_by: str,
        teacher_id: int | None = None,
    ) -> str:
        """Envoie le formulaire de disponibilités après confirmation admin.
        Sans teacher_id : campagne vers TOUS les enseignants actifs (recommandé
        pour démarrer l'établissement du planning).
        """
        if actor_role != "admin":
            return _dump({"ok": False, "error": "Action réservée à l'administration"})
        try:
            return _dump(
                await AvailabilityOutreachService(session).send(
                    channel=channel,  # type: ignore[arg-type]
                    approved_by=approved_by,
                    teacher_id=teacher_id,
                )
            )
        except ValueError as exc:
            return _dump({"ok": False, "error": str(exc)})

    @tool
    async def send_availability_form_campaign(
        channel: str,
        approved_by: str,
        teacher_ids: list[int] | None = None,
    ) -> str:
        """Campagne de collecte : envoie le formulaire à une liste d'enseignants
        (ou à tous les actifs si teacher_ids est omis). À utiliser pour lancer
        l'établissement du planning.
        """
        if actor_role != "admin":
            return _dump({"ok": False, "error": "Action réservée à l'administration"})
        try:
            return _dump(
                await AvailabilityOutreachService(session).send(
                    channel=channel,  # type: ignore[arg-type]
                    approved_by=approved_by,
                    teacher_ids=teacher_ids,
                )
            )
        except ValueError as exc:
            return _dump({"ok": False, "error": str(exc)})

    @tool
    async def generate_schedule_draft(week_start: str, requested_by: str) -> str:
        """Génère un BROUILLON d'emploi du temps pour la semaine AAAA-MM-JJ.
        Cette action ne publie rien et reste réservée à l'administration.
        """
        if actor_role != "admin":
            return _dump({"ok": False, "error": "Action réservée à l'administration"})
        item = await ScheduleGenerationService(session).generate_draft(
            date.fromisoformat(week_start), created_by=requested_by
        )
        return _dump({
            "ok": True,
            "publication_id": item.id,
            "version": item.version_number,
            "status": item.status.value,
            "report": item.generation_report,
            "notice": "Brouillon uniquement : publication humaine requise dans le back-office.",
        })

    @tool
    async def list_schedule_publications() -> str:
        """Liste les versions de planning, leurs statuts et rapports de génération."""
        if actor_role != "admin":
            return _dump({"ok": False, "error": "Action réservée à l'administration"})
        rows = await ScheduleGenerationService(session).list_publications()
        return _dump({
            "ok": True,
            "publications": [
                {
                    "id": item.id,
                    "version": item.version_number,
                    "week_start": item.week_start,
                    "status": item.status.value,
                    "report": item.generation_report,
                }
                for item in rows
            ],
        })

    @tool
    async def run_planning_cycle() -> str:
        """Avance le cycle Dashboard : à la date de collecte, contacte les profs
        via WhatsApp ; à la date de publication, génère le planning et l'envoie
        aux administrateurs (WHATSAPP_ADMINS).
        """
        if actor_role != "admin":
            return _dump({"ok": False, "error": "Action réservée à l'administration"})
        try:
            return _dump(
                await PlanningCycleService(session).run_once(
                    initiated_by="admin-agent"
                )
            )
        except ValueError as exc:
            return _dump({"ok": False, "error": str(exc)})

    @tool
    async def get_planning_cycle_status() -> str:
        """Statut du cycle planning (dates collecte/publication, phase, envois)."""
        if actor_role != "admin":
            return _dump({"ok": False, "error": "Action réservée à l'administration"})
        return _dump(await PlanningCycleService(session).status())

    @tool
    async def run_autonomous_workflow(week_start: str | None = None) -> str:
        """Fait avancer le cycle autonome de collecte, génération et publication.

        La publication n'a lieu que si AUTONOMOUS_PUBLISH_ENABLED=true et si
        tous les enseignants concernés ont confirmé le brouillon.
        """
        if actor_role != "admin":
            return _dump({"ok": False, "error": "Action réservée à l'administration"})
        parsed = date.fromisoformat(week_start) if week_start else None
        return _dump(
            await AutonomousWorkflowService(session).run_once(
                parsed, initiated_by="admin-agent"
            )
        )

    admin_tools = [
        list_teachers,
        list_levels,
        list_groups,
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
        approve_schedule_change,
        apply_schedule_change,
        confirm_presence,
        cancel_course,
        get_teacher_actions_history,
        generate_parcours_schedule_pdf,
        generate_group_schedule_pdf,
        generate_teacher_schedule_pdf,
        preview_availability_form_delivery,
        send_availability_form,
        send_availability_form_campaign,
        get_planning_cycle_status,
        run_planning_cycle,
        generate_schedule_draft,
        list_schedule_publications,
        run_autonomous_workflow,
    ]
    if actor_role != "teacher":
        return admin_tools
    return [
        get_teacher,
        get_teacher_schedule,
        get_teacher_availability,
        update_teacher_availability,
        find_impacted_entries,
        find_available_slots,
        detect_conflicts,
        propose_move_course,
        approve_schedule_change,
        apply_schedule_change,
        confirm_presence,
        cancel_course,
        generate_teacher_schedule_pdf,
    ]
