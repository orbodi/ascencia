from datetime import date, time

import pytest
from sqlalchemy import func, select

from app.domain.models import (
    Availability,
    PresenceCampaignStatus,
    PresenceRequest,
    PublicationStatus,
    SchedulePublication,
    Teacher,
    TimeSlot,
)
from app.services.presence_service import PresenceCampaignService


@pytest.mark.asyncio
async def test_partial_availability_creates_scheduler_constraints(session):
    teacher = Teacher(name="Mme Test", email="availability@example.test")
    session.add(teacher)
    session.add_all(
        [
            TimeSlot(day_of_week=0, start_time=time(8), end_time=time(10), label="Lun 08-10"),
            TimeSlot(day_of_week=1, start_time=time(14), end_time=time(16), label="Mar 14-16"),
            TimeSlot(day_of_week=2, start_time=time(8), end_time=time(10), label="Mer 08-10"),
        ]
    )
    await session.flush()
    publication = SchedulePublication(
        version_number="EDT-2030-S02-V1",
        week_start=date(2030, 1, 7),
        week_end=date(2030, 1, 13),
        status=PublicationStatus.draft,
        snapshot_json=[{"teacher_id": teacher.id}],
        generation_report={},
        created_by="admin-test",
    )
    session.add(publication)
    await session.commit()

    service = PresenceCampaignService(session)
    campaign = await service.create_campaign(publication.id, created_by="admin-test")
    token = await session.scalar(
        select(PresenceRequest.token).where(PresenceRequest.campaign_id == campaign["id"])
    )
    result = await service.record_response(
        token,
        decision="available",
        channel="whatsapp",
        response_text="lundi 08h-12h; mardi 14h-18h",
    )

    assert result["campaign"]["status"] == PresenceCampaignStatus.requires_revision.value
    assert await session.scalar(select(func.count()).select_from(Availability)) == 1
