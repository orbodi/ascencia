"""Cycle planning : dates Dashboard → collecte WhatsApp → génération → envoi admins."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import (
    AcademicLevel,
    AuditLog,
    Availability,
    Course,
    PublicationStatus,
    ScheduleEntry,
    ScheduleEntryStatus,
    SchedulePublication,
    SystemConfig,
    Teacher,
)
from app.exporters import PdfExporter
from app.services.academic_calendar import academic_week_number
from app.services.availability_outreach import AvailabilityOutreachService
from app.services.curriculum_service import CurriculumService
from app.services.generation_service import ScheduleGenerationService
from app.services.system_config import get_config_value
from app.whatsapp import WhatsAppClient
from app.whatsapp.contacts import phones_for_role

KEY_COLLECTION_START = "planning_collection_start_date"
KEY_PUBLICATION_DATE = "planning_publication_date"
KEY_TARGET_WEEK = "planning_target_week_start"
KEY_COLLECTION_SENT_AT = "planning_collection_sent_at"
KEY_PUBLICATION_SENT_AT = "planning_publication_sent_at"
KEY_LAST_PUBLICATION_ID = "planning_last_publication_id"


class PlanningCycleService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.whatsapp = WhatsAppClient()

    async def status(self) -> dict[str, Any]:
        collection_start = await self._get_date(KEY_COLLECTION_START)
        publication_date = await self._get_date(KEY_PUBLICATION_DATE)
        target_week = await self._get_date(KEY_TARGET_WEEK)
        if target_week is None and publication_date is not None:
            target_week = publication_date - timedelta(days=publication_date.weekday())
        collection_sent_at = await get_config_value(
            self.session, KEY_COLLECTION_SENT_AT, ""
        )
        publication_sent_at = await get_config_value(
            self.session, KEY_PUBLICATION_SENT_AT, ""
        )
        last_pub_id = await get_config_value(
            self.session, KEY_LAST_PUBLICATION_ID, ""
        )
        today = date.today()
        phase = self._phase(
            today=today,
            collection_start=collection_start,
            publication_date=publication_date,
            collection_sent=bool(collection_sent_at),
            publication_sent=bool(publication_sent_at),
        )
        active_teachers = (
            await self.session.scalar(
                select(Teacher).where(Teacher.is_active.is_(True)).limit(1)
            )
            is not None
        )
        responses = await self._availability_teacher_count()
        active_count = await self._active_teacher_count()
        curriculum = await self._curriculum_status(target_week)
        return {
            "ok": True,
            "today": today.isoformat(),
            "collection_start_date": collection_start.isoformat()
            if collection_start
            else None,
            "publication_date": publication_date.isoformat()
            if publication_date
            else None,
            "target_week_start": target_week.isoformat() if target_week else None,
            "collection_sent_at": collection_sent_at or None,
            "publication_sent_at": publication_sent_at or None,
            "last_publication_id": int(last_pub_id) if last_pub_id else None,
            "phase": phase,
            "availability_responses_count": responses,
            "active_teachers_count": active_count,
            "collection_complete": active_count > 0 and responses >= active_count,
            "can_run_collection": bool(
                collection_start
                and today >= collection_start
                and not collection_sent_at
                and active_teachers
            ),
            "can_run_publication": bool(
                publication_date
                and today >= publication_date
                and not publication_sent_at
            ),
            "curriculum": curriculum,
        }

    async def update_dates(
        self,
        *,
        collection_start_date: str | None,
        publication_date: str | None,
        target_week_start: str | None = None,
        updated_by: str,
    ) -> dict[str, Any]:
        collection = self._parse_date(collection_start_date)
        publication = self._parse_date(publication_date)
        target = self._parse_date(target_week_start)
        if collection and publication and publication < collection:
            raise ValueError(
                "La date de publication doit être postérieure ou égale "
                "à la date de début de collecte."
            )
        await self._upsert(
            KEY_COLLECTION_START,
            collection.isoformat() if collection else "",
            "Date de début de collecte des disponibilités",
            updated_by,
        )
        await self._upsert(
            KEY_PUBLICATION_DATE,
            publication.isoformat() if publication else "",
            "Date de publication / envoi du planning aux administrateurs",
            updated_by,
        )
        if target is not None:
            monday = target - timedelta(days=target.weekday())
            await self._upsert(
                KEY_TARGET_WEEK,
                monday.isoformat(),
                "Lundi de la semaine cible du planning généré",
                updated_by,
            )
        elif publication is not None:
            monday = publication - timedelta(days=publication.weekday())
            await self._upsert(
                KEY_TARGET_WEEK,
                monday.isoformat(),
                "Lundi de la semaine cible du planning généré",
                updated_by,
            )
        # Reset pipeline flags when dates change so the cycle can re-run.
        await self._upsert(KEY_COLLECTION_SENT_AT, "", "Horodatage collecte WhatsApp", updated_by)
        await self._upsert(KEY_PUBLICATION_SENT_AT, "", "Horodatage envoi admins", updated_by)
        await self._upsert(KEY_LAST_PUBLICATION_ID, "", "Dernière publication du cycle", updated_by)
        self.session.add(
            AuditLog(
                action="planning_cycle_dates_updated",
                payload={
                    "collection_start_date": collection.isoformat() if collection else None,
                    "publication_date": publication.isoformat() if publication else None,
                    "updated_by": updated_by,
                },
            )
        )
        await self.session.commit()
        return await self.status()

    async def run_once(self, *, initiated_by: str = "planning-cycle") -> dict[str, Any]:
        """Avance le cycle selon les dates configurées."""
        status = await self.status()
        actions: list[str] = []
        result: dict[str, Any] = {"ok": True, "actions": actions, "status_before": status}

        if status["can_run_collection"]:
            outreach = await AvailabilityOutreachService(self.session).send(
                channel="whatsapp",
                approved_by=initiated_by,
            )
            await self._upsert(
                KEY_COLLECTION_SENT_AT,
                datetime.now(timezone.utc).isoformat(),
                "Horodatage collecte WhatsApp",
                initiated_by,
            )
            actions.append("teachers_contacted_whatsapp")
            result["collection"] = outreach
            await self.session.commit()

        status = await self.status()
        if status["can_run_publication"]:
            publish = await self._generate_and_notify_admins(initiated_by=initiated_by)
            actions.append("schedule_generated_and_sent_to_admins")
            result["publication"] = publish

        result["status"] = await self.status()
        result["actions"] = actions
        if not actions:
            result["message"] = (
                "Aucune action à ce stade. Vérifiez les dates Dashboard "
                "(collecte / publication) et l'état du cycle."
            )
        return result

    async def _generate_and_notify_admins(
        self, *, initiated_by: str
    ) -> dict[str, Any]:
        status = await self.status()
        week_raw = status.get("target_week_start")
        if not week_raw:
            raise ValueError("Semaine cible non configurée")
        monday = date.fromisoformat(week_raw)

        publication = await self._latest_publication(monday)
        if publication is None or publication.status == PublicationStatus.archived:
            publication = await ScheduleGenerationService(self.session).generate_draft(
                monday, created_by=initiated_by
            )

        exporter = PdfExporter(self.session)
        from app.domain.models import StudentGroup

        levels = list(
            (
                await self.session.execute(
                    select(AcademicLevel)
                    .join(
                        StudentGroup,
                        StudentGroup.academic_level_id == AcademicLevel.id,
                    )
                    .join(Course, Course.group_id == StudentGroup.id)
                    .join(ScheduleEntry, ScheduleEntry.course_id == Course.id)
                    .where(
                        ScheduleEntry.entry_date >= monday,
                        ScheduleEntry.entry_date <= monday + timedelta(days=6),
                        ScheduleEntry.status == ScheduleEntryStatus.scheduled,
                    )
                    .distinct()
                    .order_by(AcademicLevel.id)
                )
            ).scalars().all()
        )
        pdfs: list[dict[str, Any]] = []
        for level in levels:
            pdfs.append(
                await exporter.generate_level_schedule_pdf(
                    level.id, week_start=monday
                )
            )
        if not pdfs:
            week_pdf = await exporter.generate_week_schedule_pdf(
                week_start=monday, preview=True
            )
            pdfs.append(week_pdf)

        admin_phones = sorted(phones_for_role("admin"))
        deliveries: list[dict[str, Any]] = []
        for phone in admin_phones:
            note = await self.whatsapp.send_text(
                phone,
                (
                    f"Planning publié pour la semaine du {monday.isoformat()}. "
                    f"Version {publication.version_number} — "
                    f"{len(pdfs)} fichier(s) PDF en pièce(s) jointe(s)."
                ),
            )
            deliveries.append({"to": phone, "type": "text", "result": note})
            for pdf in pdfs:
                if not pdf.get("path"):
                    continue
                doc = await self.whatsapp.send_document(
                    phone,
                    pdf["path"],
                    caption=f"EDT — {pdf.get('level_label') or pdf.get('filename')}",
                    filename=pdf.get("filename"),
                )
                deliveries.append(
                    {
                        "to": phone,
                        "type": "document",
                        "filename": pdf.get("filename"),
                        "result": doc,
                    }
                )

        now = datetime.now(timezone.utc).isoformat()
        await self._upsert(
            KEY_PUBLICATION_SENT_AT, now, "Horodatage envoi admins", initiated_by
        )
        await self._upsert(
            KEY_LAST_PUBLICATION_ID,
            str(publication.id),
            "Dernière publication du cycle",
            initiated_by,
        )
        self.session.add(
            AuditLog(
                action="planning_cycle_published_to_admins",
                payload={
                    "publication_id": publication.id,
                    "week_start": monday.isoformat(),
                    "pdf_count": len(pdfs),
                    "admin_phones": admin_phones,
                    "deliveries": deliveries,
                    "initiated_by": initiated_by,
                },
            )
        )
        await self.session.commit()
        return {
            "publication_id": publication.id,
            "version": publication.version_number,
            "week_start": monday.isoformat(),
            "pdfs": [
                {"filename": p.get("filename"), "entries_count": p.get("entries_count")}
                for p in pdfs
            ],
            "admin_recipients": admin_phones,
            "deliveries": deliveries,
        }

    async def _curriculum_status(
        self, target_week: date | None
    ) -> dict[str, Any]:
        plans = await CurriculumService(self.session).list_plans()
        week_number = (
            academic_week_number(target_week) if target_week is not None else None
        )
        levels = (
            await self.session.execute(select(AcademicLevel).order_by(AcademicLevel.code))
        ).scalars().all()
        plans_by_level = {p.academic_level_id: p for p in plans}
        coverage: list[dict[str, Any]] = []
        warnings: list[str] = []
        for level in levels:
            plan = plans_by_level.get(level.id)
            if plan is None:
                warnings.append(f"Pas de programme pour {level.code}")
                coverage.append(
                    {
                        "academic_level_id": level.id,
                        "code": level.code,
                        "has_plan": False,
                        "week_covered": False,
                        "intentions_count": 0,
                    }
                )
                continue
            covered = week_number is not None and week_number <= plan.week_count
            intentions = 0
            if week_number is not None and covered:
                intentions = sum(
                    item.sessions_count
                    for item in plan.items
                    if item.week_index == week_number
                )
                if intentions == 0:
                    warnings.append(
                        f"{level.code} : semaine {week_number} sans intention de cours"
                    )
            elif week_number is not None and not covered:
                warnings.append(
                    f"{level.code} : semaine {week_number} hors horizon "
                    f"({plan.week_count} sem.) — fallback volume"
                )
            coverage.append(
                {
                    "academic_level_id": level.id,
                    "code": level.code,
                    "has_plan": True,
                    "plan_id": plan.id,
                    "week_count": plan.week_count,
                    "semester": plan.semester,
                    "week_covered": covered,
                    "intentions_count": intentions,
                }
            )
        return {
            "academic_week_number": week_number,
            "plans_count": len(plans),
            "coverage": coverage,
            "warnings": warnings,
        }

    async def _latest_publication(
        self, monday: date
    ) -> SchedulePublication | None:
        return (
            await self.session.execute(
                select(SchedulePublication)
                .where(SchedulePublication.week_start == monday)
                .order_by(SchedulePublication.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def _active_teacher_count(self) -> int:
        from sqlalchemy import func

        return int(
            await self.session.scalar(
                select(func.count()).select_from(Teacher).where(Teacher.is_active.is_(True))
            )
            or 0
        )

    async def _availability_teacher_count(self) -> int:
        from sqlalchemy import func

        return int(
            await self.session.scalar(
                select(func.count(func.distinct(Availability.teacher_id)))
                .select_from(Availability)
                .join(Teacher, Teacher.id == Availability.teacher_id)
                .where(Teacher.is_active.is_(True))
            )
            or 0
        )

    @staticmethod
    def _phase(
        *,
        today: date,
        collection_start: date | None,
        publication_date: date | None,
        collection_sent: bool,
        publication_sent: bool,
    ) -> str:
        if publication_sent:
            return "published"
        if publication_date and today >= publication_date:
            return "ready_to_publish"
        if collection_sent:
            return "collecting"
        if collection_start and today >= collection_start:
            return "ready_to_collect"
        if collection_start and today < collection_start:
            return "scheduled"
        return "idle"

    async def _get_date(self, key: str) -> date | None:
        raw = await get_config_value(self.session, key, "")
        return self._parse_date(raw)

    @staticmethod
    def _parse_date(value: str | None) -> date | None:
        if not value or not str(value).strip():
            return None
        return date.fromisoformat(str(value).strip()[:10])

    async def _upsert(
        self, key: str, value: str, description: str, updated_by: str
    ) -> None:
        row = await self.session.scalar(
            select(SystemConfig).where(SystemConfig.key == key)
        )
        if row is None:
            self.session.add(
                SystemConfig(
                    key=key,
                    value=value,
                    description=description,
                    updated_by=updated_by,
                )
            )
        else:
            row.value = value
            row.updated_by = updated_by
            if not row.description:
                row.description = description
