from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.deps import require_admin_user
from app.admin.schemas_crud import DashboardOut
from app.api.deps import get_db
from app.domain.models import (
    AdminUser,
    Course,
    Room,
    ScheduleChange,
    ScheduleChangeStatus,
    ScheduleEntry,
    ScheduleEntryStatus,
    StudentGroup,
    Teacher,
)

router = APIRouter(prefix="/admin/dashboard", tags=["admin-dashboard"])


@router.get("", response_model=DashboardOut)
async def dashboard(
    _user: AdminUser = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db),
) -> DashboardOut:
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)

    teachers_count = await session.scalar(select(func.count()).select_from(Teacher)) or 0
    courses_count = await session.scalar(select(func.count()).select_from(Course)) or 0
    groups_count = (
        await session.scalar(select(func.count()).select_from(StudentGroup)) or 0
    )
    rooms_count = await session.scalar(select(func.count()).select_from(Room)) or 0
    pending_changes = (
        await session.scalar(
            select(func.count()).select_from(ScheduleChange).where(
                ScheduleChange.status == ScheduleChangeStatus.proposed
            )
        )
        or 0
    )
    scheduled_this_week = (
        await session.scalar(
            select(func.count())
            .select_from(ScheduleEntry)
            .where(
                ScheduleEntry.entry_date >= monday,
                ScheduleEntry.entry_date <= sunday,
                ScheduleEntry.status == ScheduleEntryStatus.scheduled,
            )
        )
        or 0
    )
    return DashboardOut(
        teachers_count=teachers_count,
        courses_count=courses_count,
        groups_count=groups_count,
        rooms_count=rooms_count,
        pending_changes=pending_changes,
        scheduled_this_week=scheduled_this_week,
    )
