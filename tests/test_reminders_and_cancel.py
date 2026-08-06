from datetime import date, time

import pytest

from app.domain.models import (
    Course,
    Room,
    ScheduleEntry,
    ScheduleEntryStatus,
    StudentGroup,
    Teacher,
    TimeSlot,
)
from app.services.planning_service import PlanningService
from app.services.reminder_service import ReminderService


async def _seed(session):
    teacher = Teacher(name="Alice", email="a@test.fr", phone_whatsapp="+3361")
    group = StudentGroup(name="L3A", student_count=30)
    room = Room(name="A101", capacity=40)
    room2 = Room(name="B202", capacity=40)
    slot = TimeSlot(
        day_of_week=0, start_time=time(8, 0), end_time=time(10, 0), label="Lun 08-10"
    )
    slot2 = TimeSlot(
        day_of_week=1, start_time=time(8, 0), end_time=time(10, 0), label="Mar 08-10"
    )
    session.add_all([teacher, group, room, room2, slot, slot2])
    await session.flush()
    course = Course(
        title="Algo",
        teacher_id=teacher.id,
        group_id=group.id,
        planned_minutes=720,
    )
    session.add(course)
    await session.flush()
    entry = ScheduleEntry(
        course_id=course.id,
        room_id=room.id,
        timeslot_id=slot.id,
        entry_date=date(2026, 8, 3),
        status=ScheduleEntryStatus.scheduled,
    )
    session.add(entry)
    await session.commit()
    return teacher, entry


@pytest.mark.asyncio
async def test_confirm_and_cancel_with_alternatives(session):
    teacher, entry = await _seed(session)
    svc = PlanningService(session)

    confirmed = await svc.confirm_presence(entry.id, teacher_id=teacher.id)
    assert confirmed["ok"] is True

    cancelled = await svc.cancel_course(
        entry_id=entry.id,
        reason="empêchement",
        teacher_id=teacher.id,
        propose_alternatives=True,
        search_days=5,
    )
    assert cancelled["cancelled"] is True
    assert cancelled["entry"]["status"] == "cancelled"
    assert isinstance(cancelled["alternatives"], list)


@pytest.mark.asyncio
async def test_presence_reminders_mock(session):
    teacher, entry = await _seed(session)
    result = await ReminderService(session).send_presence_confirmations(
        on_date=date(2026, 8, 3)
    )
    assert result["ok"] is True
    assert result["sent_count"] == 1
    assert result["reminders"][0]["entry_id"] == entry.id
    assert result["reminders"][0]["delivery"]["mock"] is True
    assert str(teacher.id) in result["reminders"][0]["message"] or teacher.name in result[
        "reminders"
    ][0]["message"]
