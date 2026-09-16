from datetime import date, time
from typing import Any

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.domain.models import PublicationStatus, ScheduleChangeStatus, ScheduleEntryStatus


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
    distribution_recipients: list[str] = Field(default_factory=list)
    student_count: int = Field(default=0, ge=0, le=2000)
    academic_level_id: int | None = None


class GroupOut(GroupIn):
    id: int
    model_config = {"from_attributes": True}


class RoomIn(BaseModel):
    name: str
    capacity: int = Field(default=30, ge=1, le=5000)


class RoomOut(RoomIn):
    id: int
    model_config = {"from_attributes": True}


class CourseIn(BaseModel):
    title: str
    teacher_id: int
    group_id: int
    duration_minutes: int = Field(default=120, ge=15, le=720)
    planned_minutes: int = Field(default=720, ge=15, le=100000)
    semester: int = Field(default=1, ge=1, le=2)
    priority: int = Field(default=0, ge=0, le=100)
    prerequisite_course_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_volumes(self) -> "CourseIn":
        self.title = self.title.strip()
        if not self.title:
            raise ValueError("L'intitulé est obligatoire")
        if self.planned_minutes < self.duration_minutes:
            raise ValueError(
                "Le volume prévu doit être au moins égal à la durée d'une séance"
            )
        if (
            self.prerequisite_course_id is not None
            and self.prerequisite_course_id <= 0
        ):
            raise ValueError("Prérequis invalide")
        return self


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
    start_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    end_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    label: str = Field(min_length=2, max_length=80)

    @model_validator(mode="after")
    def validate_time_order(self) -> "TimeSlotIn":
        start = time.fromisoformat(self.start_time)
        end = time.fromisoformat(self.end_time)
        if end <= start:
            raise ValueError("L'heure de fin doit être postérieure à l'heure de début")
        return self


class TimeSlotOut(BaseModel):
    id: int
    day_of_week: int
    start_time: str
    end_time: str
    label: str
    model_config = {"from_attributes": True}


class ScheduleEntryIn(BaseModel):
    course_id: int = Field(gt=0)
    room_id: int = Field(gt=0)
    timeslot_id: int = Field(gt=0)
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


class PublicationDraftIn(BaseModel):
    week_start: date


class PublicationPublishIn(BaseModel):
    force_presence_override: bool = False


class PublicationOut(BaseModel):
    id: int
    version_number: str
    week_start: date
    week_end: date
    status: PublicationStatus
    snapshot_json: list[dict[str, Any]]
    generation_report: dict[str, Any]
    created_by: str
    published_by: str | None = None
    created_at: str | None = None
    published_at: str | None = None
    xlsx_path: str | None = None


class ConfigItem(BaseModel):
    key: str
    value: str
    description: str | None = None


class ConfigUpdate(BaseModel):
    value: str


class CurriculumPlanCreate(BaseModel):
    academic_level_id: int = Field(gt=0)
    semester: int = Field(default=1, ge=1, le=2)
    week_count: int = Field(default=6, ge=1, le=52)


class CurriculumPlanUpdate(BaseModel):
    semester: int | None = Field(default=None, ge=1, le=2)
    week_count: int | None = Field(default=None, ge=1, le=52)


class CurriculumWeekItemIn(BaseModel):
    course_id: int = Field(gt=0)
    sessions_count: int = Field(default=1, ge=1, le=20)


class CurriculumWeekReplace(BaseModel):
    items: list[CurriculumWeekItemIn] = Field(default_factory=list)


class CurriculumWeekItemOut(BaseModel):
    id: int
    course_id: int
    course_title: str | None = None
    sessions_count: int
    duration_minutes: int | None = None


class CurriculumWeekOut(BaseModel):
    week_index: int
    items: list[CurriculumWeekItemOut]


class CurriculumPlanOut(BaseModel):
    id: int
    academic_level_id: int
    academic_level_code: str | None = None
    academic_level_label: str | None = None
    semester: int
    week_count: int
    weeks: list[CurriculumWeekOut]
    volume_warnings: list[str] = Field(default_factory=list)


class DashboardOut(BaseModel):
    teachers_count: int
    active_teachers_count: int
    teachers_with_whatsapp: int
    availability_responses_count: int
    collection_progress_percent: int
    whatsapp_coverage_percent: int
    courses_count: int
    groups_count: int
    rooms_count: int
    pending_changes: int
    approved_changes: int
    scheduled_this_week: int
    cancelled_this_week: int
    whatsapp_conversations_count: int
