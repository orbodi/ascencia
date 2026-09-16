"""Traitement des webhooks WhatsApp Cloud API."""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import AgentService
from app.config import settings
from app.domain.models import ProcessedInboundMessage, Teacher
from app.services.system_config import get_agent_name
from app.services.presence_service import PresenceCampaignService
from app.whatsapp.client import WhatsAppClient, normalize_phone
from app.whatsapp.contacts import WhatsAppPerson, find_person_by_phone
from app.whatsapp.formatting import markdown_to_whatsapp

logger = logging.getLogger(__name__)


def verify_meta_signature(raw_body: bytes, signature_header: str | None) -> bool:
    """Valide X-Hub-Signature-256 si WHATSAPP_APP_SECRET est défini."""
    secret = settings.whatsapp_app_secret
    if not secret:
        return settings.app_env.lower() not in {"production", "prod"}
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = signature_header.split("=", 1)[1]
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, expected)


def extract_inbound_messages(payload: dict[str, Any]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for msg in value.get("messages", []) or []:
                if msg.get("type") != "text":
                    continue
                text = (msg.get("text") or {}).get("body", "").strip()
                wa_from = msg.get("from", "")
                if text and wa_from:
                    messages.append(
                        {
                            "from": wa_from,
                            "text": text,
                            "message_id": msg.get("id", ""),
                        }
                    )
    return messages


class WhatsAppWebhookService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.whatsapp = WhatsAppClient()

    async def handle_inbound(self, payload: dict[str, Any]) -> dict[str, Any]:
        inbound = extract_inbound_messages(payload)
        results: list[dict[str, Any]] = []
        for msg in inbound:
            message_id = msg.get("message_id", "").strip()
            if message_id:
                receipt = ProcessedInboundMessage(
                    channel="whatsapp",
                    message_id=message_id,
                    sender_id=normalize_phone(msg["from"]),
                )
                self.session.add(receipt)
                try:
                    await self.session.flush()
                except IntegrityError:
                    await self.session.rollback()
                    results.append({
                        "message_id": message_id,
                        "ignored": True,
                        "reason": "message_deja_traite",
                    })
                    continue
            result = await self._handle_one(msg["from"], msg["text"])
            result["message_id"] = message_id or None
            results.append(result)
            await self.session.commit()
        return {
            "ok": True,
            "processed": sum(not item.get("ignored", False) for item in results),
            "ignored": sum(item.get("ignored", False) for item in results),
            "results": results,
        }

    async def _handle_one(self, wa_from: str, text: str) -> dict[str, Any]:
        presence_reply = await self._try_presence_response(wa_from, text)
        if presence_reply is not None:
            return presence_reply
        person = find_person_by_phone(wa_from)
        if person is None:
            # Fallback: numéro déjà présent en base Teacher
            teacher = await self._resolve_teacher_db(wa_from)
            if teacher is None:
                agent_name = await get_agent_name(self.session)
                reply = (
                    f"Bonjour, votre numéro n'est pas reconnu dans {agent_name}. "
                    "Contactez l'administration pour l'associer "
                    "(WHATSAPP_ADMINS / WHATSAPP_TEACHERS)."
                )
                delivery = await self.whatsapp.send_text(wa_from, reply)
                return {
                    "from": wa_from,
                    "recognized": False,
                    "reply": reply,
                    "delivery": delivery,
                }
            return await self._chat_and_reply(
                wa_from=wa_from,
                text=text,
                role="teacher",
                teacher_id=teacher.id,
                person_name=teacher.name,
            )

        role = person.role.lower().strip()
        teacher_id: int | None = None
        if role == "teacher":
            teacher = await self._resolve_teacher_from_person(person)
            teacher_id = teacher.id if teacher else None
            if teacher_id is None:
                reply = (
                    f"Bonjour {person.prenom}, votre numéro est déclaré enseignant "
                    f"mais aucune fiche Teacher ne correspond en base. "
                    f"Vérifiez le seed / le nom ({person.full_name})."
                )
                delivery = await self.whatsapp.send_text(wa_from, reply)
                return {
                    "from": wa_from,
                    "recognized": False,
                    "role": role,
                    "person": person.model_dump(),
                    "reply": reply,
                    "delivery": delivery,
                }
        elif role != "admin":
            reply = f"Rôle inconnu « {person.role} » pour {person.full_name}."
            delivery = await self.whatsapp.send_text(wa_from, reply)
            return {
                "from": wa_from,
                "recognized": False,
                "reply": reply,
                "delivery": delivery,
            }

        return await self._chat_and_reply(
            wa_from=wa_from,
            text=text,
            role=role,
            teacher_id=teacher_id,
            person_name=person.full_name,
        )

    async def _try_presence_response(
        self, wa_from: str, text: str
    ) -> dict[str, Any] | None:
        match = re.match(
            r"^\s*(CONFIRME|CONFIRMER|DISPONIBLE|INDISPONIBLE)\s+([A-Za-z0-9_-]+)"
            r"(?:\s*[:\-]\s*(.*))?\s*$",
            text,
            flags=re.IGNORECASE,
        )
        if match is None:
            return None
        action, token, reason = match.groups()
        decision = {"INDISPONIBLE": "unavailable", "DISPONIBLE": "available"}.get(
            action.upper(), "confirmed"
        )
        try:
            result = await PresenceCampaignService(self.session).record_response(
                token,
                decision=decision,
                channel="whatsapp",
                response_text=reason or text,
                sender_phone=wa_from,
            )
            if decision == "confirmed":
                reply = (
                    "Votre disponibilité complète a été confirmée. Merci."
                )
            elif decision == "available":
                reply = (
                    "Vos créneaux ont été enregistrés. Le moteur va recalculer "
                    "le planning avant sa validation finale."
                )
            else:
                reply = (
                    "Votre indisponibilité a été enregistrée. Cette version du "
                    "planning devra être révisée par l'administration."
                )
        except ValueError as exc:
            result = {"ok": False, "error": str(exc)}
            reply = f"Votre réponse n'a pas été enregistrée : {exc}"
        delivery = await self.whatsapp.send_text(wa_from, reply)
        return {
            "from": wa_from,
            "recognized": result.get("ok", False),
            "presence_response": result,
            "reply": reply,
            "delivery": delivery,
        }

    async def _chat_and_reply(
        self,
        *,
        wa_from: str,
        text: str,
        role: str,
        teacher_id: int | None,
        person_name: str,
    ) -> dict[str, Any]:
        agent_result = await AgentService(self.session).chat(
            text,
            external_user_id=normalize_phone(wa_from),
            channel="whatsapp",
            teacher_id=teacher_id,
            actor_role=role,
            whatsapp_to=wa_from,
        )
        reply = agent_result["reply"]
        if len(reply) > 3900:
            reply = reply[:3900] + "…"

        # Le prompt agent produit du Markdown (**gras**/*italique*) pensé
        # pour le rendu riche du chat back-office ; WhatsApp a sa propre
        # syntaxe (*gras*/_italique_), d'où la conversion juste avant
        # l'envoi. `reply` (stocké/retourné ci-dessous) garde le Markdown
        # d'origine, seul le texte envoyé sur WhatsApp est converti.
        delivery = await self.whatsapp.send_text(
            wa_from, markdown_to_whatsapp(reply)
        )
        return {
            "from": wa_from,
            "recognized": True,
            "role": role,
            "name": person_name,
            "teacher_id": teacher_id,
            "reply": reply,
            "delivery": delivery,
        }

    async def _resolve_teacher_from_person(
        self, person: WhatsAppPerson
    ) -> Teacher | None:
        by_phone = await self._resolve_teacher_db(person.numero)
        if by_phone is not None:
            return by_phone

        # Match sur "Prénom Nom" comme dans le seed
        full = person.full_name.casefold()
        result = await self.session.execute(select(Teacher))
        for teacher in result.scalars().all():
            if teacher.name.casefold() == full:
                # Aligne le téléphone seed avec le .env
                phone_norm = normalize_phone(person.numero)
                if normalize_phone(teacher.phone_whatsapp) != phone_norm:
                    teacher.phone_whatsapp = (
                        f"+{phone_norm}"
                        if not person.numero.startswith("+")
                        else person.numero
                    )
                    await self.session.commit()
                return teacher
        return None

    async def _resolve_teacher_db(self, wa_from: str) -> Teacher | None:
        incoming = normalize_phone(wa_from)
        result = await self.session.execute(select(Teacher))
        for teacher in result.scalars().all():
            stored = normalize_phone(teacher.phone_whatsapp)
            if not stored:
                continue
            if (
                stored == incoming
                or stored.endswith(incoming[-9:])
                or incoming.endswith(stored[-9:])
            ):
                return teacher
        return None
