from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.admin.deps import require_admin_user, require_admin_write
from app.admin.schemas_crud import CourseIn, CourseOut
from app.api.deps import get_db
from app.domain.models import (
    AdminUser,
    Course,
    ScheduleEntry,
    ScheduleEntryStatus,
    StudentGroup,
    Teacher,
)
from app.services.planning_service import PlanningService

router = APIRouter(prefix="/admin/courses", tags=["admin-courses"])


def _format_hours(minutes: int) -> str:
    return PlanningService._format_hours(minutes)


async def _validate_course_refs(
    session: AsyncSession,
    body: CourseIn,
    *,
    course_id: int | None = None,
) -> None:
    teacher = await session.get(Teacher, body.teacher_id)
    if teacher is None:
        raise HTTPException(status_code=400, detail="Enseignant introuvable")
    if course_id is None and not teacher.is_active:
        raise HTTPException(
            status_code=400,
            detail="Impossible d'assigner un enseignant archivé",
        )

    group = await session.get(StudentGroup, body.group_id)
    if group is None:
        raise HTTPException(status_code=400, detail="Groupe introuvable")

    if body.prerequisite_course_id is not None:
        if course_id is not None and body.prerequisite_course_id == course_id:
            raise HTTPException(
                status_code=400,
                detail="Un cours ne peut pas être son propre prérequis",
            )
        prereq = await session.get(Course, body.prerequisite_course_id)
        if prereq is None:
            raise HTTPException(status_code=400, detail="Prérequis introuvable")


def _course_payload(course: Course, *, sessions: int = 0) -> dict:
    done = sessions * course.duration_minutes
    remaining = max(0, course.planned_minutes - done)
    return {
        "id": course.id,
        "title": course.title,
        "teacher_id": course.teacher_id,
        "group_id": course.group_id,
        "duration_minutes": course.duration_minutes,
        "planned_minutes": course.planned_minutes,
        "semester": course.semester,
        "priority": course.priority,
        "prerequisite_course_id": course.prerequisite_course_id,
        "teacher_name": course.teacher.name if course.teacher else None,
        "group_name": course.group.name if course.group else None,
        "scheduled_sessions": sessions,
        "planned_hours": _format_hours(course.planned_minutes),
        "hours_done": _format_hours(done),
        "hours_remaining": _format_hours(remaining),
    }


@router.get("", response_model=list[CourseOut])
async def list_courses(
    _user: AdminUser = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db),
) -> list[dict]:
    result = await session.execute(
        select(Course)
        .options(selectinload(Course.teacher), selectinload(Course.group))
        .order_by(Course.title)
    )
    courses = list(result.scalars().all())
    entries = (
        await session.execute(
            select(ScheduleEntry).where(
                ScheduleEntry.status == ScheduleEntryStatus.scheduled
            )
        )
    ).scalars().all()
    count_by: dict[int, int] = {}
    for e in entries:
        count_by[e.course_id] = count_by.get(e.course_id, 0) + 1

    return [
        _course_payload(c, sessions=count_by.get(c.id, 0)) for c in courses
    ]


@router.post("", response_model=CourseOut, status_code=status.HTTP_201_CREATED)
async def create_course(
    body: CourseIn,
    _user: AdminUser = Depends(require_admin_write),
    session: AsyncSession = Depends(get_db),
) -> dict:
    await _validate_course_refs(session, body)
    course = Course(**body.model_dump())
    session.add(course)
    await session.commit()
    result = await session.execute(
        select(Course)
        .where(Course.id == course.id)
        .options(selectinload(Course.teacher), selectinload(Course.group))
    )
    course = result.scalar_one()
    return _course_payload(course, sessions=0)


@router.patch("/{course_id}", response_model=CourseOut)
async def update_course(
    course_id: int,
    body: CourseIn,
    _user: AdminUser = Depends(require_admin_write),
    session: AsyncSession = Depends(get_db),
) -> dict:
    course = await session.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Cours introuvable")
    await _validate_course_refs(session, body, course_id=course_id)
    for key, value in body.model_dump().items():
        setattr(course, key, value)
    await session.commit()
    result = await session.execute(
        select(Course)
        .where(Course.id == course_id)
        .options(selectinload(Course.teacher), selectinload(Course.group))
    )
    course = result.scalar_one()
    count = int(
        await session.scalar(
            select(func.count())
            .select_from(ScheduleEntry)
            .where(
                ScheduleEntry.course_id == course_id,
                ScheduleEntry.status == ScheduleEntryStatus.scheduled,
            )
        )
        or 0
    )
    return _course_payload(course, sessions=count)


@router.delete("/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_course(
    course_id: int,
    _user: AdminUser = Depends(require_admin_write),
    session: AsyncSession = Depends(get_db),
) -> None:
    course = await session.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Cours introuvable")
    await session.delete(course)
    await session.commit()
