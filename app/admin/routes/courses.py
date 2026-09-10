from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.admin.deps import require_admin_user, require_admin_write
from app.admin.schemas_crud import CourseIn, CourseOut
from app.api.deps import get_db
from app.domain.models import AdminUser, Course, ScheduleEntry, ScheduleEntryStatus
from app.services.planning_service import PlanningService

router = APIRouter(prefix="/admin/courses", tags=["admin-courses"])


def _format_hours(minutes: int) -> str:
    return PlanningService._format_hours(minutes)


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

    out: list[dict] = []
    for c in courses:
        sessions = count_by.get(c.id, 0)
        done = sessions * c.duration_minutes
        remaining = max(0, c.planned_minutes - done)
        out.append(
            {
                "id": c.id,
                "title": c.title,
                "teacher_id": c.teacher_id,
                "group_id": c.group_id,
                "duration_minutes": c.duration_minutes,
                "planned_minutes": c.planned_minutes,
                "semester": c.semester,
                "priority": c.priority,
                "prerequisite_course_id": c.prerequisite_course_id,
                "teacher_name": c.teacher.name if c.teacher else None,
                "group_name": c.group.name if c.group else None,
                "scheduled_sessions": sessions,
                "planned_hours": _format_hours(c.planned_minutes),
                "hours_done": _format_hours(done),
                "hours_remaining": _format_hours(remaining),
            }
        )
    return out


@router.post("", response_model=CourseOut, status_code=status.HTTP_201_CREATED)
async def create_course(
    body: CourseIn,
    _user: AdminUser = Depends(require_admin_write),
    session: AsyncSession = Depends(get_db),
) -> dict:
    course = Course(**body.model_dump())
    session.add(course)
    await session.commit()
    await session.refresh(course)
    return {
        **body.model_dump(),
        "id": course.id,
        "scheduled_sessions": 0,
        "planned_hours": _format_hours(course.planned_minutes),
        "hours_done": "0H",
        "hours_remaining": _format_hours(course.planned_minutes),
    }


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
    for key, value in body.model_dump().items():
        setattr(course, key, value)
    await session.commit()
    await session.refresh(course)
    return {
        **body.model_dump(),
        "id": course.id,
        "planned_hours": _format_hours(course.planned_minutes),
    }


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
