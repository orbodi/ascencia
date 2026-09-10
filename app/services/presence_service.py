from __future__ import annotations

import secrets
import re
import unicodedata
from datetime import datetime, time, timedelta, timezone
from typing import Any
from urllib.parse import quote

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.domain.models import (
    AuditLog,
    Availability,
    PresenceCampaign,
    PresenceCampaignStatus,
    PresenceRequest,
    PresenceResponseStatus,
    PublicationStatus,
    SchedulePublication,
    Teacher,
    TimeSlot,
)
from app.notifications import EmailClient
from app.whatsapp.client import WhatsAppClient, normalize_phone


class PresenceCampaignService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.email = EmailClient()
        self.whatsapp = WhatsAppClient()

    async def create_campaign(
        self,
        publication_id: int,
        *,
        created_by: str,
        channels: list[str] | None = None,
    ) -> dict[str, Any]:
        publication = await self.session.get(SchedulePublication, publication_id)
        if publication is None:
            raise ValueError("Version de planning introuvable")
        if publication.status != PublicationStatus.draft:
            raise ValueError("La confirmation concerne uniquement un brouillon")
        existing = await self.session.scalar(
            select(PresenceCampaign).where(
                PresenceCampaign.publication_id == publication_id
            )
        )
        if existing is not None:
            return await self.campaign_details(existing.id)

        teacher_ids = sorted(
            {
                int(item["teacher_id"])
                for item in publication.snapshot_json
                if item.get("teacher_id") is not None
            }
        )
        if not teacher_ids:
            raise ValueError("Aucun enseignant n'est présent dans ce brouillon")

        selected_channels = channels or ["email", "whatsapp"]
        selected_channels = [
            item for item in selected_channels if item in {"email", "whatsapp"}
        ]
        if not selected_channels:
            raise ValueError("Au moins un canal de confirmation est requis")

        campaign = PresenceCampaign(
            publication_id=publication_id,
            status=PresenceCampaignStatus.open,
            channels=selected_channels,
            deadline_at=datetime.now(timezone.utc)
            + timedelta(hours=settings.presence_response_hours),
            created_by=created_by,
        )
        self.session.add(campaign)
        await self.session.flush()
        for teacher_id in teacher_ids:
            self.session.add(
                PresenceRequest(
                    campaign_id=campaign.id,
                    teacher_id=teacher_id,
                    token=secrets.token_urlsafe(18),
                    status=PresenceResponseStatus.pending,
                    sent_channels=[],
                )
            )
        self.session.add(
            AuditLog(
                action="presence_campaign_created",
                payload={
                    "campaign_id": campaign.id,
                    "publication_id": publication_id,
                    "teacher_ids": teacher_ids,
                    "channels": selected_channels,
                    "created_by": created_by,
                },
            )
        )
        await self.session.commit()
        return await self.campaign_details(campaign.id)

    async def send_campaign(
        self,
        campaign_id: int,
        *,
        resend_pending: bool = True,
        max_attempts: int | None = None,
    ) -> dict[str, Any]:
        campaign = await self.session.get(PresenceCampaign, campaign_id)
        if campaign is None:
            raise ValueError("Campagne de confirmation introuvable")
        publication = await self.session.get(
            SchedulePublication, campaign.publication_id
        )
        assert publication is not None
        requests = (
            await self.session.execute(
                select(PresenceRequest)
                .where(PresenceRequest.campaign_id == campaign_id)
                .order_by(PresenceRequest.id)
            )
        ).scalars().all()

        deliveries: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc)
        for request in requests:
            if request.status != PresenceResponseStatus.pending:
                continue
            if request.attempt_count > 0 and not resend_pending:
                continue
            if max_attempts is not None and request.attempt_count >= max_attempts:
                continue
            teacher = await self.session.get(Teacher, request.teacher_id)
            if teacher is None:
                continue
            confirm_url = self._response_url(request.token, "confirmed")
            available_url = self._response_url(request.token, "available")
            unavailable_url = self._response_url(request.token, "unavailable")
            subject = (
                f"Ascencia Keyce — confirmation {publication.version_number}"
            )
            message = (
                f"Bonjour {teacher.name},\n\n"
                f"Nous préparons l'emploi du temps de la semaine du "
                f"{publication.week_start.strftime('%d/%m/%Y')} au "
                f"{publication.week_end.strftime('%d/%m/%Y')}.\n\n"
                "Merci d'indiquer vos disponibilités :\n"
                f"- Disponible toute la semaine : {confirm_url}\n"
                f"- Disponible sur certains créneaux : {available_url}\n"
                f"- Je suis indisponible : {unavailable_url}\n\n"
                "Pour préciser des créneaux, répondez sur WhatsApp :\n"
                f"DISPONIBLE {request.token} : lundi 08h-12h; mardi 14h-18h\n"
                f"CONFIRME {request.token}\n"
                f"ou INDISPONIBLE {request.token} : votre motif\n\n"
                f"Référence : {publication.version_number}."
            )
            successful_channels = set(request.sent_channels or [])
            if "email" in campaign.channels:
                result = await self.email.send(teacher.email, subject, message)
                deliveries.append(
                    {
                        "teacher_id": teacher.id,
                        "teacher_name": teacher.name,
                        "channel": "email",
                        "result": result,
                    }
                )
                if result.get("ok"):
                    successful_channels.add("email")
            if "whatsapp" in campaign.channels:
                if not teacher.phone_whatsapp:
                    result = {"ok": False, "error": "Numéro WhatsApp manquant"}
                elif settings.whatsapp_presence_template_name:
                    result = await self.whatsapp.send_template(
                        teacher.phone_whatsapp,
                        settings.whatsapp_presence_template_name,
                        components=[
                            {
                                "type": "body",
                                "parameters": [
                                    {"type": "text", "text": teacher.name},
                                    {
                                        "type": "text",
                                        "text": publication.version_number,
                                    },
                                    {"type": "text", "text": request.token},
                                ],
                            }
                        ],
                    )
                else:
                    result = await self.whatsapp.send_text(
                        teacher.phone_whatsapp, message
                    )
                deliveries.append(
                    {
                        "teacher_id": teacher.id,
                        "teacher_name": teacher.name,
                        "channel": "whatsapp",
                        "result": result,
                    }
                )
                if result.get("ok"):
                    successful_channels.add("whatsapp")
            request.sent_channels = sorted(successful_channels)
            request.attempt_count += 1
            request.last_sent_at = now

        self.session.add(
            AuditLog(
                action="presence_campaign_sent",
                payload={"campaign_id": campaign_id, "deliveries": deliveries},
            )
        )
        await self.session.commit()
        return {
            "ok": all(item["result"].get("ok", False) for item in deliveries)
            if deliveries
            else True,
            "campaign_id": campaign_id,
            "deliveries": deliveries,
            "summary": await self.campaign_details(campaign_id),
        }

    async def record_response(
        self,
        token: str,
        *,
        decision: str,
        channel: str,
        response_text: str | None = None,
        sender_phone: str | None = None,
    ) -> dict[str, Any]:
        request = await self.session.scalar(
            select(PresenceRequest).where(PresenceRequest.token == token.strip())
        )
        if request is None:
            raise ValueError("Référence de confirmation invalide")
        campaign = await self.session.get(PresenceCampaign, request.campaign_id)
        assert campaign is not None
        publication = await self.session.get(
            SchedulePublication, campaign.publication_id
        )
        assert publication is not None
        if sender_phone:
            teacher = await self.session.get(Teacher, request.teacher_id)
            if teacher is None or normalize_phone(teacher.phone_whatsapp) != normalize_phone(
                sender_phone
            ):
                raise ValueError("Ce numéro ne correspond pas à la demande de confirmation")
        if publication.status != PublicationStatus.draft:
            raise ValueError("Cette version a déjà été publiée ou archivée")

        normalized = decision.lower().strip()
        if normalized not in {"confirmed", "available", "unavailable"}:
            raise ValueError("Réponse attendue : confirmed, available ou unavailable")

        marker = f"[campagne:{campaign.id}]"
        await self.session.execute(
            delete(Availability).where(
                Availability.teacher_id == request.teacher_id,
                Availability.reason.like(f"{marker}%"),
            )
        )
        if normalized == "confirmed":
            request.status = PresenceResponseStatus.confirmed
        elif normalized == "available":
            windows = self._parse_availability_windows(response_text or "")
            if not windows:
                raise ValueError(
                    "Créneaux non compris. Exemple : lundi 08h-12h; mardi 14h-18h"
                )
            slots = (await self.session.execute(select(TimeSlot))).scalars().all()
            for slot in slots:
                accepted = any(
                    slot.start_time >= start and slot.end_time <= end
                    for start, end in windows.get(slot.day_of_week, [])
                )
                if accepted:
                    continue
                target_date = publication.week_start + timedelta(days=slot.day_of_week)
                if target_date > publication.week_end:
                    continue
                self.session.add(
                    Availability(
                        teacher_id=request.teacher_id,
                        start_at=datetime.combine(target_date, slot.start_time, tzinfo=timezone.utc),
                        end_at=datetime.combine(target_date, slot.end_time, tzinfo=timezone.utc),
                        reason=f"{marker} hors disponibilité déclarée"[:255],
                        is_blocking=True,
                    )
                )
            request.status = PresenceResponseStatus.confirmed
            request.response_text = (response_text or "")[:500]
        else:
            request.status = PresenceResponseStatus.unavailable
            reason = (response_text or "Indisponibilité signalée").strip()[:220]
            request.response_text = reason
            self.session.add(
                Availability(
                    teacher_id=request.teacher_id,
                    start_at=datetime.combine(
                        publication.week_start, time.min, tzinfo=timezone.utc
                    ),
                    end_at=datetime.combine(
                        publication.week_end, time.max, tzinfo=timezone.utc
                    ),
                    reason=f"{marker} {reason}"[:255],
                    is_blocking=True,
                )
            )
        request.responded_at = datetime.now(timezone.utc)
        request.response_channel = channel
        if response_text and normalized == "confirmed":
            request.response_text = response_text[:500]

        await self.session.flush()
        await self._refresh_campaign_status(campaign)
        self.session.add(
            AuditLog(
                action="presence_response_recorded",
                payload={
                    "campaign_id": campaign.id,
                    "publication_id": publication.id,
                    "teacher_id": request.teacher_id,
                    "status": request.status.value,
                    "channel": channel,
                },
            )
        )
        await self.session.commit()
        details = await self.campaign_details(campaign.id)
        return {
            "ok": True,
            "teacher_id": request.teacher_id,
            "status": request.status.value,
            "campaign": details,
        }

    async def campaign_details(self, campaign_id: int) -> dict[str, Any]:
        campaign = await self.session.get(PresenceCampaign, campaign_id)
        if campaign is None:
            raise ValueError("Campagne de confirmation introuvable")
        publication = await self.session.get(
            SchedulePublication, campaign.publication_id
        )
        rows = (
            await self.session.execute(
                select(PresenceRequest)
                .where(PresenceRequest.campaign_id == campaign_id)
                .order_by(PresenceRequest.id)
            )
        ).scalars().all()
        requests: list[dict[str, Any]] = []
        for item in rows:
            teacher = await self.session.get(Teacher, item.teacher_id)
            requests.append(
                {
                    "id": item.id,
                    "teacher_id": item.teacher_id,
                    "teacher_name": teacher.name if teacher else None,
                    "teacher_email": teacher.email if teacher else None,
                    "teacher_phone": teacher.phone_whatsapp if teacher else None,
                    "status": item.status.value,
                    "sent_channels": item.sent_channels,
                    "attempt_count": item.attempt_count,
                    "last_sent_at": item.last_sent_at.isoformat()
                    if item.last_sent_at
                    else None,
                    "responded_at": item.responded_at.isoformat()
                    if item.responded_at
                    else None,
                    "response_channel": item.response_channel,
                    "response_text": item.response_text,
                }
            )
        counts = {
            status.value: sum(1 for row in rows if row.status == status)
            for status in PresenceResponseStatus
        }
        return {
            "id": campaign.id,
            "publication_id": campaign.publication_id,
            "version_number": publication.version_number if publication else None,
            "status": campaign.status.value,
            "channels": campaign.channels,
            "deadline_at": campaign.deadline_at.isoformat()
            if campaign.deadline_at
            else None,
            "created_by": campaign.created_by,
            "counts": counts,
            "requests": requests,
        }

    async def campaign_for_publication(
        self, publication_id: int
    ) -> dict[str, Any] | None:
        campaign = await self.session.scalar(
            select(PresenceCampaign).where(
                PresenceCampaign.publication_id == publication_id
            )
        )
        if campaign is None:
            return None
        return await self.campaign_details(campaign.id)

    async def _refresh_campaign_status(self, campaign: PresenceCampaign) -> None:
        statuses = list(
            (
                await self.session.execute(
                    select(PresenceRequest.status).where(
                        PresenceRequest.campaign_id == campaign.id
                    )
                )
            ).scalars().all()
        )
        has_collected_constraints = bool(
            await self.session.scalar(
                select(Availability.id).where(
                    Availability.reason.like(f"[campagne:{campaign.id}]%")
                ).limit(1)
            )
        )
        if any(item == PresenceResponseStatus.unavailable for item in statuses) or has_collected_constraints:
            campaign.status = PresenceCampaignStatus.requires_revision
        elif statuses and all(
            item == PresenceResponseStatus.confirmed for item in statuses
        ):
            campaign.status = PresenceCampaignStatus.ready
        else:
            campaign.status = PresenceCampaignStatus.open

    @staticmethod
    def _response_url(token: str, decision: str) -> str:
        base = settings.public_base_url.rstrip("/")
        return (
            f"{base}/presence/respond/{quote(token)}?decision={quote(decision)}"
        )

    @staticmethod
    def _parse_availability_windows(value: str) -> dict[int, list[tuple[time, time]]]:
        normalized = unicodedata.normalize("NFKD", value.lower())
        normalized = "".join(char for char in normalized if not unicodedata.combining(char))
        days = {"lundi": 0, "mardi": 1, "mercredi": 2, "jeudi": 3, "vendredi": 4, "samedi": 5, "dimanche": 6}
        result: dict[int, list[tuple[time, time]]] = {}
        pattern = re.compile(
            r"(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\s+"
            r"(\d{1,2})(?:h|:)(\d{2})?\s*(?:-|a|à)\s*"
            r"(\d{1,2})(?:h|:)(\d{2})?"
        )
        for day, start_hour, start_minute, end_hour, end_minute in pattern.findall(normalized):
            start = time(int(start_hour), int(start_minute or 0))
            end = time(int(end_hour), int(end_minute or 0))
            if start < end:
                result.setdefault(days[day], []).append((start, end))
        return result
