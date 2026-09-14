"""Collecte des disponibilités enseignants (formulaire e-mail / WhatsApp)."""

from __future__ import annotations

from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import AuditLog, Teacher
from app.notifications import EmailClient
from app.services.system_config import get_availability_form_url
from app.whatsapp import WhatsAppClient

Channel = Literal["email", "whatsapp", "both"]


class AvailabilityOutreachService:
    """Envoi du formulaire de disponibilités avant génération du planning."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.email = EmailClient()
        self.whatsapp = WhatsAppClient()

    async def preview(
        self,
        *,
        teacher_id: int | None = None,
        channel: Channel = "both",
    ) -> dict[str, Any]:
        form_url = await get_availability_form_url(self.session)
        teachers = await self._resolve_teachers(teacher_id)
        return {
            "ok": bool(form_url) and bool(teachers),
            "form_url": form_url or None,
            "channel": channel,
            "count": len(teachers),
            "teachers": [
                {
                    "id": teacher.id,
                    "name": teacher.name,
                    "email": teacher.email,
                    "phone_whatsapp": teacher.phone_whatsapp,
                    "can_email": bool(teacher.email),
                    "can_whatsapp": bool(teacher.phone_whatsapp),
                }
                for teacher in teachers
            ],
            "error": None
            if form_url and teachers
            else (
                "Lien de formulaire non configuré"
                if not form_url
                else "Aucun enseignant cible"
            ),
        }

    async def send(
        self,
        *,
        channel: Channel,
        approved_by: str,
        teacher_id: int | None = None,
        teacher_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        if channel not in {"email", "whatsapp", "both"}:
            raise ValueError("Canal invalide (email | whatsapp | both)")
        if not approved_by.strip():
            raise ValueError("Validation administrateur requise (approved_by)")

        form_url = await get_availability_form_url(self.session)
        if not form_url and channel == "email":
            raise ValueError(
                "Lien de formulaire non configuré "
                "(AVAILABILITY_FORM_URL ou Configuration IA)"
            )
        if not form_url and channel == "both":
            # WhatsApp partira en mode conversationnel ; e-mail exige le lien.
            pass

        teachers = await self._resolve_teachers(teacher_id, teacher_ids)
        if not teachers:
            raise ValueError("Aucun enseignant actif à contacter")

        if channel in {"email", "both"} and not form_url:
            raise ValueError(
                "Lien de formulaire requis pour l'e-mail "
                "(AVAILABILITY_FORM_URL ou Configuration IA)"
            )

        deliveries: list[dict[str, Any]] = []
        for teacher in teachers:
            result = await self._send_one(
                teacher, channel=channel, form_url=form_url or ""
            )
            deliveries.append(result)

        ok_count = sum(1 for item in deliveries if item.get("ok"))
        self.session.add(
            AuditLog(
                action="availability_form_campaign_sent",
                payload={
                    "channel": channel,
                    "approved_by": approved_by,
                    "teacher_ids": [t.id for t in teachers],
                    "ok_count": ok_count,
                    "deliveries": deliveries,
                },
            )
        )
        await self.session.commit()
        return {
            "ok": ok_count == len(deliveries),
            "form_url": form_url,
            "channel": channel,
            "approved_by": approved_by,
            "targeted": len(deliveries),
            "delivered_ok": ok_count,
            "deliveries": deliveries,
        }

    async def _send_one(
        self,
        teacher: Teacher,
        *,
        channel: Channel,
        form_url: str,
    ) -> dict[str, Any]:
        subject = "Ascencia Keyce — formulaire de disponibilités"
        if form_url:
            message = (
                f"Bonjour {teacher.name},\n\n"
                "Nous préparons le prochain emploi du temps. "
                "Merci de renseigner vos indisponibilités via ce formulaire :\n"
                f"{form_url}\n\n"
                "Vous pouvez aussi répondre sur WhatsApp avec vos créneaux "
                "indisponibles (ex. : lundi 08h-12h ; mardi après-midi).\n\n"
                "L'administration prendra en compte vos contraintes avant génération."
            )
        else:
            message = (
                f"Bonjour {teacher.name},\n\n"
                "La collecte de vos disponibilités pour le prochain planning commence. "
                "Merci de répondre sur WhatsApp avec vos créneaux d'indisponibilité "
                "(exemple : lundi 08h-12h ; mercredi après-midi).\n\n"
                "Ascencia Keyce — planification."
            )
        channels: dict[str, Any] = {}
        if channel in {"email", "both"}:
            if not form_url:
                channels["email"] = {
                    "ok": False,
                    "error": "Lien formulaire manquant",
                }
            else:
                channels["email"] = await self.email.send(
                    teacher.email, subject, message
                )
        if channel in {"whatsapp", "both"}:
            if not teacher.phone_whatsapp:
                channels["whatsapp"] = {
                    "ok": False,
                    "error": "Numéro WhatsApp manquant",
                }
            else:
                channels["whatsapp"] = await self.whatsapp.send_text(
                    teacher.phone_whatsapp, message
                )
        return {
            "ok": all(item.get("ok") for item in channels.values()),
            "teacher_id": teacher.id,
            "teacher_name": teacher.name,
            "channels": channels,
        }

    async def _resolve_teachers(
        self,
        teacher_id: int | None = None,
        teacher_ids: list[int] | None = None,
    ) -> list[Teacher]:
        if teacher_id is not None:
            teacher = await self.session.get(Teacher, teacher_id)
            if teacher is None or not teacher.is_active:
                return []
            return [teacher]

        stmt = select(Teacher).where(Teacher.is_active.is_(True)).order_by(Teacher.name)
        if teacher_ids:
            stmt = stmt.where(Teacher.id.in_(teacher_ids))
        return list((await self.session.execute(stmt)).scalars().all())
