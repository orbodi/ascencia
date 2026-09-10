from datetime import date, time

import pytest
from sqlalchemy import func, select

from app.domain.models import (
    Course,
    PresenceRequest,
    PublicationStatus,
    Room,
    ScheduleEntry,
    StudentGroup,
    Teacher,
    TimeSlot,
)
from app.services.generation_service import ScheduleGenerationService
from app.services.presence_service import PresenceCampaignService


@pytest.mark.asyncio
async def test_generate_then_publish_schedule_version(session):
    teacher = Teacher(name="Enseignant test", email="teacher@example.test")
    group = StudentGroup(name="Groupe test", student_count=24)
    room = Room(name="Salle test", capacity=30)
    slot = TimeSlot(
        day_of_week=0,
        start_time=time(8, 0),
        end_time=time(10, 0),
        label="Lun 08-10",
    )
    session.add_all([teacher, group, room, slot])
    await session.flush()
    session.add(
        Course(
            title="Cours test",
            teacher_id=teacher.id,
            group_id=group.id,
            duration_minutes=120,
            planned_minutes=600,
        )
    )
    await session.commit()

    service = ScheduleGenerationService(session)
    draft = await service.generate_draft(date(2030, 1, 7), created_by="admin-test")
    assert draft.status == PublicationStatus.draft
    assert draft.generation_report["generated_count"] == 1
    assert len(draft.snapshot_json) == 1

    campaign_service = PresenceCampaignService(session)
    campaign = await campaign_service.create_campaign(
        draft.id, created_by="admin-test", channels=["email"]
    )
    for request in campaign["requests"]:
        token = await session.scalar(
            select(PresenceRequest.token).where(PresenceRequest.id == request["id"])
        )
        assert token
        await campaign_service.record_response(
            token, decision="confirmed", channel="test"
        )

    published = await service.publish(draft.id, published_by="admin-test")
    assert published.status == PublicationStatus.published
    assert published.published_by == "admin-test"
    count = await session.scalar(select(func.count()).select_from(ScheduleEntry))
    assert count == 1


@pytest.mark.asyncio
async def test_generation_respects_course_prerequisite(session):
    teacher = Teacher(name="Enseignant prérequis", email="prerequisite@example.test")
    group = StudentGroup(name="Groupe prérequis", student_count=20)
    room = Room(name="Salle prérequis", capacity=25)
    slot = TimeSlot(day_of_week=0, start_time=time(8), end_time=time(10), label="Lun 08-10 prérequis")
    session.add_all([teacher, group, room, slot])
    await session.flush()
    algorithmics = Course(
        title="Algorithmique",
        teacher_id=teacher.id,
        group_id=group.id,
        duration_minutes=120,
        planned_minutes=240,
        priority=10,
    )
    session.add(algorithmics)
    await session.flush()
    session.add(
        Course(
            title="Python",
            teacher_id=teacher.id,
            group_id=group.id,
            duration_minutes=120,
            planned_minutes=240,
            prerequisite_course_id=algorithmics.id,
        )
    )
    await session.commit()

    draft = await ScheduleGenerationService(session).generate_draft(
        date(2030, 1, 7), created_by="admin-test"
    )

    assert [item["course_title"] for item in draft.snapshot_json] == ["Algorithmique"]
    assert any("prérequis" in item["reason"] for item in draft.generation_report["unscheduled"])
