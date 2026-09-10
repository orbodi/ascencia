from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.domain.models import (
    AuditLog,
    DeliveryStatus,
    DistributionDelivery,
    PublicationStatus,
    SchedulePublication,
    StudentGroup,
)
from app.exporters import ExcelExporter, PdfExporter
from app.whatsapp.client import WhatsAppClient


class PublicationDistributionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.whatsapp = WhatsAppClient()

    async def distribute(self, publication_id: int) -> dict[str, Any]:
        publication = await self.session.get(SchedulePublication, publication_id)
        if publication is None:
            raise ValueError("Version de planning introuvable")
        if publication.status != PublicationStatus.published:
            raise ValueError("Seule une version publiée peut être diffusée")

        excel_result = ExcelExporter().generate_publication_workbook(publication)
        publication.xlsx_path = excel_result["path"]
        group_ids = sorted(
            {
                int(item["group_id"])
                for item in publication.snapshot_json
                if item.get("group_id") is not None
            }
        )
        results: list[dict[str, Any]] = []
        pdfs: list[dict[str, Any]] = []
        for group_id in group_ids:
            group = await self.session.get(StudentGroup, group_id)
            if group is None:
                continue
            pdf = await PdfExporter(self.session).generate_group_schedule_pdf(
                group_id, week_start=publication.week_start
            )
            pdfs.append(pdf)
            recipients = [
                item.strip()
                for item in (group.distribution_recipients or [])
                if item and item.strip()
            ]
            channel = "whatsapp_individual_list"
            if not recipients and settings.whatsapp_mock and group.whatsapp_group_id:
                recipients = [group.whatsapp_group_id]
                channel = "whatsapp_group_mock"

            if not recipients:
                delivery = DistributionDelivery(
                    publication_id=publication.id,
                    group_id=group.id,
                    channel="whatsapp_pdf",
                    recipient=group.whatsapp_group_id or "non_configure",
                    status=DeliveryStatus.skipped,
                    artifact_path=pdf["path"],
                    provider_response={},
                    error=(
                        "Aucun destinataire individuel configuré. L'identifiant de "
                        "groupe n'est pas utilisé en mode réel par ce client."
                    ),
                )
                self.session.add(delivery)
                results.append(
                    {
                        "group_id": group.id,
                        "group_name": group.name,
                        "status": "skipped",
                        "error": delivery.error,
                    }
                )
                continue

            for recipient in recipients:
                provider = await self.whatsapp.send_document(
                    recipient,
                    pdf["path"],
                    caption=(
                        f"{settings.university_name} — emploi du temps "
                        f"{group.name} — {publication.version_number}"
                    ),
                    filename=pdf["filename"],
                )
                status = (
                    DeliveryStatus.sent if provider.get("ok") else DeliveryStatus.failed
                )
                delivery = DistributionDelivery(
                    publication_id=publication.id,
                    group_id=group.id,
                    channel=channel,
                    recipient=recipient,
                    status=status,
                    artifact_path=pdf["path"],
                    provider_response=provider,
                    error=None if provider.get("ok") else str(provider.get("error")),
                    sent_at=datetime.now(timezone.utc)
                    if provider.get("ok")
                    else None,
                )
                self.session.add(delivery)
                results.append(
                    {
                        "group_id": group.id,
                        "group_name": group.name,
                        "recipient": recipient,
                        "status": status.value,
                        "mock": provider.get("mock", False),
                        "error": delivery.error,
                    }
                )

        self.session.add(
            AuditLog(
                action="schedule_artifacts_distributed",
                payload={
                    "publication_id": publication.id,
                    "version": publication.version_number,
                    "xlsx_path": publication.xlsx_path,
                    "deliveries": results,
                },
            )
        )
        await self.session.commit()
        return {
            "ok": all(item["status"] == "sent" for item in results)
            if results
            else False,
            "publication_id": publication.id,
            "version": publication.version_number,
            "xlsx": excel_result,
            "pdfs": pdfs,
            "sent_count": sum(item["status"] == "sent" for item in results),
            "failed_count": sum(item["status"] == "failed" for item in results),
            "skipped_count": sum(item["status"] == "skipped" for item in results),
            "deliveries": results,
        }

    async def history(self, publication_id: int) -> list[dict[str, Any]]:
        rows = (
            await self.session.execute(
                select(DistributionDelivery)
                .where(DistributionDelivery.publication_id == publication_id)
                .order_by(DistributionDelivery.id.desc())
            )
        ).scalars().all()
        return [
            {
                "id": item.id,
                "group_id": item.group_id,
                "channel": item.channel,
                "recipient": item.recipient,
                "status": item.status.value,
                "artifact_path": item.artifact_path,
                "error": item.error,
                "created_at": item.created_at.isoformat() if item.created_at else None,
                "sent_at": item.sent_at.isoformat() if item.sent_at else None,
            }
            for item in rows
        ]
