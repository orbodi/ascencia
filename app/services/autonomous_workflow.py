from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.domain.models import (
    AuditLog,
    PresenceCampaign,
    PresenceCampaignStatus,
    PresenceRequest,
    PresenceResponseStatus,
    PublicationStatus,
    SchedulePublication,
)
from app.services.distribution_service import PublicationDistributionService
from app.services.generation_service import ScheduleGenerationService
from app.services.presence_service import PresenceCampaignService


_workflow_lock = asyncio.Lock()


class AutonomousWorkflowService:
    """Pilote un cycle hebdomadaire idempotent, traçable et sous contraintes."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def status(self, week_start: date | None = None) -> dict[str, Any]:
        monday = self._target_monday(week_start)
        publication = await self._latest_publication(monday)
        campaign = None
        if publication is not None:
            campaign = await self.session.scalar(
                select(PresenceCampaign).where(
                    PresenceCampaign.publication_id == publication.id
                )
            )
        return {
            "enabled": settings.autonomous_mode_enabled,
            "automatic_publication": settings.autonomous_publish_enabled,
            "week_start": monday.isoformat(),
            "publication": self._publication_summary(publication),
            "campaign": await self._campaign_summary(campaign),
        }

    async def run_once(
        self,
        week_start: date | None = None,
        *,
        initiated_by: str = "autonomous-agent",
    ) -> dict[str, Any]:
        async with _workflow_lock:
            return await self._run_once(week_start, initiated_by=initiated_by)

    async def _run_once(
        self,
        week_start: date | None = None,
        *,
        initiated_by: str = "autonomous-agent",
    ) -> dict[str, Any]:
        """Fait avancer le processus d'un état sans contourner les validations."""

        monday = self._target_monday(week_start)
        publication = await self._latest_publication(monday)

        if publication is not None and publication.status == PublicationStatus.published:
            return await self._result(
                "already_published", monday, publication, None, []
            )

        actions: list[str] = []
        if publication is None or publication.status == PublicationStatus.archived:
            publication = await ScheduleGenerationService(self.session).generate_draft(
                monday, created_by=initiated_by
            )
            actions.append("draft_generated")

        campaign = await self.session.scalar(
            select(PresenceCampaign).where(
                PresenceCampaign.publication_id == publication.id
            )
        )
        presence = PresenceCampaignService(self.session)

        if campaign is None:
            created = await presence.create_campaign(
                publication.id,
                created_by=initiated_by,
                channels=self._channels(),
            )
            campaign = await self.session.get(PresenceCampaign, int(created["id"]))
            actions.append("presence_campaign_created")
            await presence.send_campaign(campaign.id, resend_pending=False)
            actions.append("presence_requests_sent")
            return await self._result(
                "waiting_for_confirmations", monday, publication, campaign, actions
            )

        if campaign.status == PresenceCampaignStatus.requires_revision:
            publication.status = PublicationStatus.archived
            self.session.add(
                AuditLog(
                    action="autonomous_draft_archived_for_revision",
                    payload={
                        "publication_id": publication.id,
                        "campaign_id": campaign.id,
                        "initiated_by": initiated_by,
                    },
                )
            )
            await self.session.commit()
            actions.append("obsolete_draft_archived")

            publication = await ScheduleGenerationService(self.session).generate_draft(
                monday, created_by=initiated_by
            )
            actions.append("draft_regenerated")
            created = await presence.create_campaign(
                publication.id,
                created_by=initiated_by,
                channels=self._channels(),
            )
            campaign = await self.session.get(PresenceCampaign, int(created["id"]))
            actions.append("presence_campaign_recreated")
            await presence.send_campaign(campaign.id, resend_pending=False)
            actions.append("presence_requests_sent")
            return await self._result(
                "regenerated_after_availability_change",
                monday,
                publication,
                campaign,
                actions,
            )

        if campaign.status == PresenceCampaignStatus.ready:
            if not settings.autonomous_publish_enabled:
                return await self._result(
                    "ready_for_manual_publication",
                    monday,
                    publication,
                    campaign,
                    actions,
                )
            publication = await ScheduleGenerationService(self.session).publish(
                publication.id, published_by=initiated_by
            )
            actions.append("schedule_published")
            distribution = await PublicationDistributionService(self.session).distribute(
                publication.id
            )
            actions.append("artifacts_generated_and_distributed")
            result = await self._result(
                "published_and_distributed",
                monday,
                publication,
                campaign,
                actions,
            )
            result["distribution"] = distribution
            return result

        if campaign.status == PresenceCampaignStatus.open:
            if await self._reminder_due(campaign.id):
                sent = await presence.send_campaign(
                    campaign.id,
                    resend_pending=True,
                    max_attempts=settings.autonomous_max_reminders,
                )
                if sent["deliveries"]:
                    actions.append("pending_confirmations_reminded")
            return await self._result(
                "waiting_for_confirmations", monday, publication, campaign, actions
            )

        return await self._result(
            "campaign_completed", monday, publication, campaign, actions
        )

    async def _latest_publication(self, monday: date) -> SchedulePublication | None:
        return await self.session.scalar(
            select(SchedulePublication)
            .where(SchedulePublication.week_start == monday)
            .order_by(SchedulePublication.id.desc())
            .limit(1)
        )

    async def _reminder_due(self, campaign_id: int) -> bool:
        pending = list(
            (
                await self.session.execute(
                    select(PresenceRequest).where(
                        PresenceRequest.campaign_id == campaign_id,
                        PresenceRequest.status == PresenceResponseStatus.pending,
                    )
                )
            ).scalars().all()
        )
        if not pending:
            return False
        now = datetime.now(timezone.utc)
        threshold = now - timedelta(hours=settings.autonomous_reminder_hours)
        for item in pending:
            if item.attempt_count >= settings.autonomous_max_reminders:
                continue
            last_sent = item.last_sent_at
            if last_sent is not None and last_sent.tzinfo is None:
                last_sent = last_sent.replace(tzinfo=timezone.utc)
            if last_sent is None or last_sent <= threshold:
                return True
        return False

    async def _campaign_summary(
        self, campaign: PresenceCampaign | None
    ) -> dict[str, Any] | None:
        if campaign is None:
            return None
        return await PresenceCampaignService(self.session).campaign_details(campaign.id)

    async def _result(
        self,
        state: str,
        monday: date,
        publication: SchedulePublication | None,
        campaign: PresenceCampaign | None,
        actions: list[str],
    ) -> dict[str, Any]:
        return {
            "ok": True,
            "state": state,
            "week_start": monday.isoformat(),
            "actions": actions,
            "publication": self._publication_summary(publication),
            "campaign": await self._campaign_summary(campaign),
        }

    @staticmethod
    def _publication_summary(
        publication: SchedulePublication | None,
    ) -> dict[str, Any] | None:
        if publication is None:
            return None
        return {
            "id": publication.id,
            "version": publication.version_number,
            "status": publication.status.value,
            "generated_count": publication.generation_report.get("generated_count", 0),
            "unscheduled_count": publication.generation_report.get("unscheduled_count", 0),
        }

    @staticmethod
    def _target_monday(value: date | None) -> date:
        target = value or (
            date.today() + timedelta(weeks=settings.autonomous_target_week_offset)
        )
        return target - timedelta(days=target.weekday())

    @staticmethod
    def _channels() -> list[str]:
        channels = [
            item.strip().lower()
            for item in settings.autonomous_channels.split(",")
            if item.strip().lower() in {"email", "whatsapp"}
        ]
        return channels or ["email", "whatsapp"]
