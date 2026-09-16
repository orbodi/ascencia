from datetime import date, time

import pytest

from app.config import settings
from app.domain.models import (
    AcademicLevel,
    Course,
    CurriculumPlan,
    CurriculumWeekItem,
    Room,
    StudentGroup,
    Teacher,
    TimeSlot,
)
from app.services.generation_service import ScheduleGenerationService


@pytest.mark.asyncio
async def test_generation_follows_curriculum_week_intentions(session, monkeypatch):
    monkeypatch.setattr(settings, "semester_start_date", date(2030, 1, 7))

    level = AcademicLevel(
        code="B1-INFO",
        label="B1 Informatique",
        degree="L",
        year=1,
        speciality="Info",
    )
    teacher = Teacher(name="Prof curriculum", email="curric@example.test")
    session.add_all([level, teacher])
    await session.flush()

    group = StudentGroup(
        name="B1 Info A",
        student_count=20,
        academic_level_id=level.id,
    )
    room = Room(name="Salle curriculum", capacity=30)
    slots = [
        TimeSlot(
            day_of_week=0, start_time=time(8, 0), end_time=time(10, 0), label="Lun 08-10"
        ),
        TimeSlot(
            day_of_week=1, start_time=time(8, 0), end_time=time(10, 0), label="Mar 08-10"
        ),
        TimeSlot(
            day_of_week=2, start_time=time(8, 0), end_time=time(10, 0), label="Mer 08-10"
        ),
    ]
    session.add_all([group, room, *slots])
    await session.flush()

    algo = Course(
        title="Algo",
        teacher_id=teacher.id,
        group_id=group.id,
        duration_minutes=120,
        planned_minutes=600,
        semester=1,
        priority=5,
    )
    db = Course(
        title="Bases de données",
        teacher_id=teacher.id,
        group_id=group.id,
        duration_minutes=120,
        planned_minutes=600,
        semester=1,
        priority=4,
    )
    other = Course(
        title="Hors plan",
        teacher_id=teacher.id,
        group_id=group.id,
        duration_minutes=120,
        planned_minutes=600,
        semester=1,
        priority=10,
    )
    session.add_all([algo, db, other])
    await session.flush()

    plan = CurriculumPlan(
        academic_level_id=level.id, semester=1, week_count=6
    )
    session.add(plan)
    await session.flush()
    session.add_all(
        [
            CurriculumWeekItem(
                plan_id=plan.id, week_index=1, course_id=algo.id, sessions_count=1
            ),
            CurriculumWeekItem(
                plan_id=plan.id, week_index=1, course_id=db.id, sessions_count=1
            ),
            CurriculumWeekItem(
                plan_id=plan.id, week_index=2, course_id=algo.id, sessions_count=2
            ),
        ]
    )
    await session.commit()

    draft_w1 = await ScheduleGenerationService(session).generate_draft(
        date(2030, 1, 7), created_by="test"
    )
    titles_w1 = sorted(item["course_title"] for item in draft_w1.snapshot_json)
    assert titles_w1 == ["Algo", "Bases de données"]
    assert draft_w1.generation_report["curriculum_mode"] is True
    assert draft_w1.generation_report["academic_week_number"] == 1
    assert draft_w1.generation_report["skipped_not_in_plan_count"] >= 1

    draft_w2 = await ScheduleGenerationService(session).generate_draft(
        date(2030, 1, 14), created_by="test"
    )
    titles_w2 = [item["course_title"] for item in draft_w2.snapshot_json]
    assert titles_w2.count("Algo") == 2
    assert "Bases de données" not in titles_w2
    assert draft_w2.generation_report["academic_week_number"] == 2


@pytest.mark.asyncio
async def test_generation_fallback_when_week_outside_plan(session, monkeypatch):
    monkeypatch.setattr(settings, "semester_start_date", date(2030, 1, 7))

    level = AcademicLevel(
        code="B2-INFO", label="B2", degree="L", year=2, speciality="Info"
    )
    teacher = Teacher(name="Prof fallback", email="fallback@example.test")
    session.add_all([level, teacher])
    await session.flush()
    group = StudentGroup(
        name="B2 Info", student_count=18, academic_level_id=level.id
    )
    room = Room(name="Salle fallback", capacity=25)
    slot = TimeSlot(
        day_of_week=0, start_time=time(8, 0), end_time=time(10, 0), label="Lun fb"
    )
    session.add_all([group, room, slot])
    await session.flush()
    course = Course(
        title="Cours fallback",
        teacher_id=teacher.id,
        group_id=group.id,
        duration_minutes=120,
        planned_minutes=600,
        semester=1,
    )
    session.add(course)
    await session.flush()
    plan = CurriculumPlan(academic_level_id=level.id, semester=1, week_count=2)
    session.add(plan)
    await session.commit()

    # Semaine académique 3 > week_count 2 → fallback volume
    draft = await ScheduleGenerationService(session).generate_draft(
        date(2030, 1, 21), created_by="test"
    )
    assert draft.generation_report["curriculum_mode"] is False
    assert draft.generation_report["generated_count"] == 1
    assert any(
        "hors programme" in w.lower() or "hors horizon" in w.lower()
        for w in draft.generation_report["curriculum_warnings"]
    )
