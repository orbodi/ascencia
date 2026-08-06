from datetime import date, time
from pathlib import Path

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


def _weasyprint_ready() -> bool:
    try:
        import weasyprint  # noqa: F401

        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _weasyprint_ready(),
    reason="WeasyPrint indisponible (dépendances natives manquantes hors Docker)",
)


async def _seed(session):
    from app.exporters import PdfExporter

    teacher = Teacher(name="Alice", email="a@test.fr", phone_whatsapp="+3361")
    group = StudentGroup(name="L3A", student_count=30)
    room = Room(name="A101", capacity=40)
    slot = TimeSlot(
        day_of_week=0, start_time=time(8, 0), end_time=time(10, 0), label="Lun 08-10"
    )
    session.add_all([teacher, group, room, slot])
    await session.flush()
    course = Course(title="Algo", teacher_id=teacher.id, group_id=group.id)
    session.add(course)
    await session.flush()
    session.add(
        ScheduleEntry(
            course_id=course.id,
            room_id=room.id,
            timeslot_id=slot.id,
            entry_date=date(2026, 8, 3),
            status=ScheduleEntryStatus.scheduled,
        )
    )
    await session.commit()
    return teacher, group, PdfExporter


@pytest.mark.asyncio
async def test_generate_teacher_and_group_pdf(session):
    teacher, group, PdfExporter = await _seed(session)
    exporter = PdfExporter(session)

    teacher_pdf = await exporter.generate_teacher_schedule_pdf(
        teacher.id, week_start=date(2026, 8, 3)
    )
    assert teacher_pdf["ok"] is True
    assert Path(teacher_pdf["path"]).exists()
    assert Path(teacher_pdf["path"]).stat().st_size > 0

    group_pdf = await exporter.generate_group_schedule_pdf(
        group.id, week_start=date(2026, 8, 3)
    )
    assert group_pdf["ok"] is True
    assert Path(group_pdf["path"]).exists()
