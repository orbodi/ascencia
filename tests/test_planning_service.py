from datetime import date, datetime, time, timezone

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


async def _seed_minimal(session):
    alice = Teacher(name="Alice", email="alice@test.fr", phone_whatsapp="+3361")
    bruno = Teacher(name="Bruno", email="bruno@test.fr", phone_whatsapp="+3362")
    group = StudentGroup(name="L3A", student_count=30, whatsapp_group_id="g1")
    room_a = Room(name="A101", capacity=40)
    room_b = Room(name="B202", capacity=40)
    slot_wed = TimeSlot(
        day_of_week=2, start_time=time(8, 0), end_time=time(10, 0), label="Mer 08-10"
    )
    slot_thu = TimeSlot(
        day_of_week=3, start_time=time(8, 0), end_time=time(10, 0), label="Jeu 08-10"
    )
    session.add_all([alice, bruno, group, room_a, room_b, slot_wed, slot_thu])
    await session.flush()

    course = Course(title="Algo", teacher_id=alice.id, group_id=group.id)
    session.add(course)
    await session.flush()

    entry = ScheduleEntry(
        course_id=course.id,
        room_id=room_a.id,
        timeslot_id=slot_wed.id,
        entry_date=date(2026, 8, 5),
        status=ScheduleEntryStatus.scheduled,
    )
    session.add(entry)
    await session.commit()
    return {
        "alice": alice,
        "entry": entry,
        "room_b": room_b,
        "slot_thu": slot_thu,
    }


@pytest.mark.asyncio
async def test_impacted_entries_and_propose_apply(session):
    data = await _seed_minimal(session)
    svc = PlanningService(session)

    impacted = await svc.find_impacted_entries(data["alice"].id, date(2026, 8, 5))
    assert len(impacted) == 1
    assert impacted[0]["course_title"] == "Algo"

    await svc.update_teacher_availability(
        teacher_id=data["alice"].id,
        start_at=datetime(2026, 8, 5, 0, 0, tzinfo=timezone.utc),
        end_at=datetime(2026, 8, 5, 23, 59, tzinfo=timezone.utc),
        reason="absent mercredi",
    )

    options = await svc.find_available_slots(
        entry_id=data["entry"].id,
        search_start=date(2026, 8, 5),
        search_end=date(2026, 8, 7),
        limit=3,
    )
    assert options, "Au moins une alternative attendue"
    # le mercredi doit être exclu à cause de l'indisponibilité
    assert all(o["entry_date"] != "2026-08-05" for o in options)

    choice = options[0]
    proposal = await svc.propose_move_course(
        entry_id=data["entry"].id,
        entry_date=date.fromisoformat(choice["entry_date"]),
        timeslot_id=choice["timeslot_id"],
        room_id=choice["room_id"],
        proposed_by="test",
    )
    assert proposal["ok"] is True

    with pytest.raises(ValueError, match="approbation humaine"):
        await svc.apply_schedule_change(proposal["change_id"])

    approved = await svc.approve_schedule_change(
        proposal["change_id"], approved_by="responsable-test"
    )
    assert approved["status"] == "approved"

    applied = await svc.apply_schedule_change(proposal["change_id"])
    assert applied["ok"] is True
    assert applied["entry"]["entry_date"] == choice["entry_date"]


@pytest.mark.asyncio
async def test_manual_entry_rejects_wrong_day(session):
    data = await _seed_minimal(session)
    svc = PlanningService(session)

    wrong_day = await svc.validate_schedule_entry(
        course_id=data["entry"].course_id,
        room_id=data["room_b"].id,
        timeslot_id=data["slot_thu"].id,
        entry_date=date(2026, 8, 5),
    )
    assert wrong_day[0]["code"] == "timeslot_day_mismatch"
