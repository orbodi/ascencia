from datetime import date, time

import pytest
from sqlalchemy import select

from app.config import settings
from app.domain.models import (
    Course,
    PresenceRequest,
    PublicationStatus,
    Room,
    StudentGroup,
    Teacher,
    TimeSlot,
)
from app.services.autonomous_workflow import AutonomousWorkflowService
from app.services.distribution_service import PublicationDistributionService
from app.services.presence_service import PresenceCampaignService


async def _seed_minimal_week(session) -> None:
    teacher = Teacher(
        name="Enseignant autonomie",
        email="autonomie@example.test",
        phone_whatsapp="+22890000000",
    )
    group = StudentGroup(
        name="Groupe autonomie",
        student_count=20,
        whatsapp_group_id="22891111111",
    )
    room = Room(name="Salle autonomie", capacity=30)
    slot = TimeSlot(
        day_of_week=0,
        start_time=time(8),
        end_time=time(10),
        label="Lun 08-10 autonomie",
    )
    session.add_all([teacher, group, room, slot])
    await session.flush()
    session.add(
        Course(
            title="Cours autonomie",
            teacher_id=teacher.id,
            group_id=group.id,
            duration_minutes=120,
            planned_minutes=120,
        )
    )
    await session.commit()


@pytest.mark.asyncio
async def test_autonomous_cycle_creates_draft_campaign_and_requests(session):
    await _seed_minimal_week(session)

    result = await AutonomousWorkflowService(session).run_once(
        date(2030, 1, 7), initiated_by="test-agent"
    )

    assert result["state"] == "waiting_for_confirmations"
    assert result["actions"] == [
        "draft_generated",
        "presence_campaign_created",
        "presence_requests_sent",
    ]
    assert result["publication"]["generated_count"] == 1
    assert result["campaign"]["counts"]["pending"] == 1
    assert result["campaign"]["requests"][0]["attempt_count"] == 1


@pytest.mark.asyncio
async def test_autonomous_cycle_publishes_only_after_confirmation(
    session, monkeypatch
):
    await _seed_minimal_week(session)
    monkeypatch.setattr(settings, "autonomous_publish_enabled", True)

    service = AutonomousWorkflowService(session)
    first = await service.run_once(date(2030, 1, 7), initiated_by="test-agent")
    request = await session.scalar(select(PresenceRequest))
    assert request is not None
    await PresenceCampaignService(session).record_response(
        request.token, decision="confirmed", channel="test"
    )

    async def fake_distribute(self, publication_id: int):
        return {"ok": True, "publication_id": publication_id, "sent_count": 1}

    monkeypatch.setattr(PublicationDistributionService, "distribute", fake_distribute)
    second = await service.run_once(date(2030, 1, 7), initiated_by="test-agent")

    assert first["state"] == "waiting_for_confirmations"
    assert second["state"] == "published_and_distributed"
    assert second["publication"]["status"] == PublicationStatus.published.value
    assert second["distribution"]["ok"] is True
