from datetime import date
from typing import Any

from pydantic import BaseModel, EmailStr, Field

from app.domain.models import ScheduleChangeStatus, ScheduleEntryStatus


class LevelIn(BaseModel):
    code: str
    label: str
    degree: str = Field(pattern="^[LMD]$")
    year: int = Field(ge=1, le=3)
    speciality: str | None = None


class LevelOut(LevelIn):
    id: int
    model_config = {"from_attributes": True}


class TeacherIn(BaseModel):
    name: str
    email: EmailStr
    phone_whatsapp: str | None = None
    is_active: bool = True


class TeacherOut(TeacherIn):
    id: int
    model_config = {"from_attributes": True}


class GroupIn(BaseModel):
    name: str
    whatsapp_group_id: str | None = None
    student_count: int = 0
    academic_level_id: int | None = None


class GroupOut(GroupIn):
    id: int
    model_config = {"from_attributes": True}


class RoomIn(BaseModel):
    name: str
    capacity: int = 30


class RoomOut(RoomIn):
    id: int
    model_config = {"from_attributes": True}


class CourseIn(BaseModel):
    title: str
    teacher_id: int
    group_id: int
    duration_minutes: int = 120
    planned_minutes: int = 720


class CourseOut(CourseIn):
    id: int
    hours_done: str | None = None
    hours_remaining: str | None = None
    planned_hours: str | None = None
    scheduled_sessions: int | None = None
    teacher_name: str | None = None
    group_name: str | None = None
    model_config = {"from_attributes": True}


class TimeSlotIn(BaseModel):
    day_of_week: int = Field(ge=0, le=6)
    start_time: str  # HH:MM
    end_time: str
    label: str


class TimeSlotOut(BaseModel):
    id: int
    day_of_week: int
    start_time: str
    end_time: str
    label: str
    model_config = {"from_attributes": True}


class ScheduleEntryIn(BaseModel):
    course_id: int
    room_id: int
    timeslot_id: int
    entry_date: date
    status: ScheduleEntryStatus = ScheduleEntryStatus.scheduled


class ScheduleEntryOut(BaseModel):
    id: int
    course_id: int
    room_id: int
    timeslot_id: int
    entry_date: date
    status: ScheduleEntryStatus
    course_title: str | None = None
    teacher_name: str | None = None
    group_name: str | None = None
    room_name: str | None = None
    timeslot_label: str | None = None
    model_config = {"from_attributes": True}


class ChangeOut(BaseModel):
    id: int
    entry_id: int
    before_json: dict[str, Any]
    after_json: dict[str, Any]
    status: ScheduleChangeStatus
    proposed_by: str
    created_at: str | None = None
    model_config = {"from_attributes": True}


class ConfigItem(BaseModel):
    key: str
    value: str
    description: str | None = None


class ConfigUpdate(BaseModel):
    value: str


class DashboardOut(BaseModel):
    teachers_count: int
    courses_count: int
    groups_count: int
    rooms_count: int
    pending_changes: int
    scheduled_this_week: int
