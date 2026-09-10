from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.deps import require_admin_user
from app.admin.schemas_crud import DashboardOut
from app.api.deps import get_db
from app.domain.models import (
    AdminUser,
    Availability,
    ConversationHistory,
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
    active_teachers_count = (
        await session.scalar(
            select(func.count()).select_from(Teacher).where(Teacher.is_active.is_(True))
        )
        or 0
    )
    teachers_with_whatsapp = (
        await session.scalar(
            select(func.count())
            .select_from(Teacher)
            .where(
                Teacher.is_active.is_(True),
                Teacher.phone_whatsapp.is_not(None),
                Teacher.phone_whatsapp != "",
            )
        )
        or 0
    )
    availability_responses_count = (
        await session.scalar(
            select(func.count(func.distinct(Availability.teacher_id)))
            .select_from(Availability)
            .join(Teacher, Teacher.id == Availability.teacher_id)
            .where(Teacher.is_active.is_(True))
        )
        or 0
    )
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
    cancelled_this_week = (
        await session.scalar(
            select(func.count())
            .select_from(ScheduleEntry)
            .where(
                ScheduleEntry.entry_date >= monday,
                ScheduleEntry.entry_date <= sunday,
                ScheduleEntry.status == ScheduleEntryStatus.cancelled,
            )
        )
        or 0
    )
    approved_changes = (
        await session.scalar(
            select(func.count()).select_from(ScheduleChange).where(
                ScheduleChange.status.in_(
                    [ScheduleChangeStatus.approved, ScheduleChangeStatus.applied]
                )
            )
        )
        or 0
    )
    whatsapp_conversations_count = (
        await session.scalar(
            select(func.count(func.distinct(ConversationHistory.external_user_id)))
            .select_from(ConversationHistory)
            .where(ConversationHistory.channel == "whatsapp")
        )
        or 0
    )
    collection_progress_percent = (
        round(availability_responses_count * 100 / active_teachers_count)
        if active_teachers_count
        else 0
    )
    whatsapp_coverage_percent = (
        round(teachers_with_whatsapp * 100 / active_teachers_count)
        if active_teachers_count
        else 0
    )
    return DashboardOut(
        teachers_count=teachers_count,
        active_teachers_count=active_teachers_count,
        teachers_with_whatsapp=teachers_with_whatsapp,
        availability_responses_count=availability_responses_count,
        collection_progress_percent=collection_progress_percent,
        whatsapp_coverage_percent=whatsapp_coverage_percent,
        courses_count=courses_count,
        groups_count=groups_count,
        rooms_count=rooms_count,
        pending_changes=pending_changes,
        approved_changes=approved_changes,
        scheduled_this_week=scheduled_this_week,
        cancelled_this_week=cancelled_this_week,
        whatsapp_conversations_count=whatsapp_conversations_count,
    )
