from __future__ import annotations

import enum
from datetime import date, datetime, time
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.models.base import Base


class ScheduleEntryStatus(str, enum.Enum):
    scheduled = "scheduled"
    cancelled = "cancelled"
    moved = "moved"


class ScheduleChangeStatus(str, enum.Enum):
    proposed = "proposed"
    approved = "approved"
    rejected = "rejected"
    applied = "applied"


class PublicationStatus(str, enum.Enum):
    draft = "draft"
    published = "published"
    archived = "archived"


class PresenceCampaignStatus(str, enum.Enum):
    open = "open"
    ready = "ready"
    requires_revision = "requires_revision"
    completed = "completed"


class PresenceResponseStatus(str, enum.Enum):
    pending = "pending"
    confirmed = "confirmed"
    unavailable = "unavailable"


class DeliveryStatus(str, enum.Enum):
    pending = "pending"
    sent = "sent"
    failed = "failed"
    skipped = "skipped"


class AdminRole(str, enum.Enum):
    superadmin = "superadmin"
    admin = "admin"
    viewer = "viewer"


class AcademicLevel(Base):
    """Niveau / parcours (ex: L3-INFO, M1-IA)."""

    __tablename__ = "academic_levels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    degree: Mapped[str] = mapped_column(String(8), nullable=False)  # L | M | D
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    speciality: Mapped[Optional[str]] = mapped_column(String(120))

    groups: Mapped[list[StudentGroup]] = relationship(back_populates="academic_level")
    curriculum_plans: Mapped[list[CurriculumPlan]] = relationship(
        back_populates="academic_level"
    )


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(180), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[AdminRole] = mapped_column(
        Enum(
            AdminRole,
            name="admin_role",
            native_enum=True,
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        default=AdminRole.admin,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SystemConfig(Base):
    __tablename__ = "system_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    updated_by: Mapped[Optional[str]] = mapped_column(String(80))


class Teacher(Base):
    __tablename__ = "teachers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(180), unique=True, nullable=False)
    phone_whatsapp: Mapped[Optional[str]] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    courses: Mapped[list[Course]] = relationship(back_populates="teacher")
    availabilities: Mapped[list[Availability]] = relationship(back_populates="teacher")


class StudentGroup(Base):
    __tablename__ = "student_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    whatsapp_group_id: Mapped[Optional[str]] = mapped_column(String(64))
    distribution_recipients: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )
    student_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    academic_level_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("academic_levels.id"), nullable=True
    )

    academic_level: Mapped[Optional[AcademicLevel]] = relationship(
        back_populates="groups"
    )
    courses: Mapped[list[Course]] = relationship(back_populates="group")


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=30)

    schedule_entries: Mapped[list[ScheduleEntry]] = relationship(back_populates="room")


class TimeSlot(Base):
    """Grille horaire fixe (ex: Lundi 08:00-10:00). day_of_week: 0=lundi … 6=dimanche."""

    __tablename__ = "time_slots"
    __table_args__ = (
        UniqueConstraint(
            "day_of_week", "start_time", "end_time", name="uq_timeslot_day_hours"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    label: Mapped[str] = mapped_column(String(40), nullable=False)

    schedule_entries: Mapped[list[ScheduleEntry]] = relationship(
        back_populates="timeslot"
    )


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"), nullable=False)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("student_groups.id"), nullable=False
    )
    duration_minutes: Mapped[int] = mapped_column(Integer, default=120, nullable=False)
    planned_minutes: Mapped[int] = mapped_column(Integer, default=720, nullable=False)
    semester: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    prerequisite_course_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("courses.id"), nullable=True
    )

    teacher: Mapped[Teacher] = relationship(back_populates="courses")
    group: Mapped[StudentGroup] = relationship(back_populates="courses")
    schedule_entries: Mapped[list[ScheduleEntry]] = relationship(
        back_populates="course"
    )
    prerequisite: Mapped[Optional[Course]] = relationship(
        remote_side="Course.id", foreign_keys=[prerequisite_course_id]
    )
    curriculum_items: Mapped[list[CurriculumWeekItem]] = relationship(
        back_populates="course"
    )


class CurriculumPlan(Base):
    """Programme pédagogique multi-semaines pour un parcours / semestre."""

    __tablename__ = "curriculum_plans"
    __table_args__ = (
        UniqueConstraint(
            "academic_level_id",
            "semester",
            name="uq_curriculum_plan_level_semester",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    academic_level_id: Mapped[int] = mapped_column(
        ForeignKey("academic_levels.id"), nullable=False
    )
    semester: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    week_count: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    academic_level: Mapped[AcademicLevel] = relationship(
        back_populates="curriculum_plans"
    )
    items: Mapped[list[CurriculumWeekItem]] = relationship(
        back_populates="plan",
        cascade="all, delete-orphan",
    )


class CurriculumWeekItem(Base):
    """Intention de placement : cours × nb de séances pour une semaine académique."""

    __tablename__ = "curriculum_week_items"
    __table_args__ = (
        UniqueConstraint(
            "plan_id",
            "week_index",
            "course_id",
            name="uq_curriculum_week_course",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("curriculum_plans.id", ondelete="CASCADE"), nullable=False
    )
    week_index: Mapped[int] = mapped_column(Integer, nullable=False)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False)
    sessions_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    plan: Mapped[CurriculumPlan] = relationship(back_populates="items")
    course: Mapped[Course] = relationship(back_populates="curriculum_items")


class ScheduleEntry(Base):
    __tablename__ = "schedule_entries"
    __table_args__ = (
        UniqueConstraint(
            "room_id",
            "timeslot_id",
            "entry_date",
            name="uq_room_slot_date",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), nullable=False)
    timeslot_id: Mapped[int] = mapped_column(ForeignKey("time_slots.id"), nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[ScheduleEntryStatus] = mapped_column(
        Enum(
            ScheduleEntryStatus,
            name="schedule_entry_status",
            native_enum=True,
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        default=ScheduleEntryStatus.scheduled,
        nullable=False,
    )

    course: Mapped[Course] = relationship(back_populates="schedule_entries")
    room: Mapped[Room] = relationship(back_populates="schedule_entries")
    timeslot: Mapped[TimeSlot] = relationship(back_populates="schedule_entries")
    changes: Mapped[list[ScheduleChange]] = relationship(back_populates="entry")


class Availability(Base):
    __tablename__ = "availabilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"), nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(255))
    is_blocking: Mapped[bool] = mapped_column(default=True, nullable=False)

    teacher: Mapped[Teacher] = relationship(back_populates="availabilities")


class ScheduleChange(Base):
    __tablename__ = "schedule_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_id: Mapped[int] = mapped_column(
        ForeignKey("schedule_entries.id"), nullable=False
    )
    before_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    after_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[ScheduleChangeStatus] = mapped_column(
        Enum(
            ScheduleChangeStatus,
            name="schedule_change_status",
            native_enum=True,
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        default=ScheduleChangeStatus.proposed,
        nullable=False,
    )
    proposed_by: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    entry: Mapped[ScheduleEntry] = relationship(back_populates="changes")


class ConversationHistory(Base):
    __tablename__ = "conversation_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel: Mapped[str] = mapped_column(String(40), nullable=False)
    external_user_id: Mapped[str] = mapped_column(String(80), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ProcessedInboundMessage(Base):
    """Reçu technique empêchant le retraitement d'un webhook déjà livré."""

    __tablename__ = "processed_inbound_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel: Mapped[str] = mapped_column(String(40), nullable=False)
    message_id: Mapped[str] = mapped_column(String(180), unique=True, nullable=False)
    sender_id: Mapped[str] = mapped_column(String(80), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SchedulePublication(Base):
    """Version traçable d'un planning généré pour une semaine."""

    __tablename__ = "schedule_publications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_number: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    week_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[PublicationStatus] = mapped_column(
        Enum(
            PublicationStatus,
            name="publication_status",
            native_enum=True,
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        default=PublicationStatus.draft,
        nullable=False,
    )
    snapshot_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    generation_report: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_by: Mapped[str] = mapped_column(String(80), nullable=False)
    published_by: Mapped[Optional[str]] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    xlsx_path: Mapped[Optional[str]] = mapped_column(String(500))


class PresenceCampaign(Base):
    __tablename__ = "presence_campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    publication_id: Mapped[int] = mapped_column(
        ForeignKey("schedule_publications.id"), unique=True, nullable=False
    )
    status: Mapped[PresenceCampaignStatus] = mapped_column(
        Enum(
            PresenceCampaignStatus,
            name="presence_campaign_status",
            native_enum=True,
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        default=PresenceCampaignStatus.open,
        nullable=False,
    )
    channels: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    deadline_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class PresenceRequest(Base):
    __tablename__ = "presence_requests"
    __table_args__ = (
        UniqueConstraint(
            "campaign_id", "teacher_id", name="uq_presence_campaign_teacher"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("presence_campaigns.id"), nullable=False
    )
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"), nullable=False)
    token: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    status: Mapped[PresenceResponseStatus] = mapped_column(
        Enum(
            PresenceResponseStatus,
            name="presence_response_status",
            native_enum=True,
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        default=PresenceResponseStatus.pending,
        nullable=False,
    )
    sent_channels: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    response_channel: Mapped[Optional[str]] = mapped_column(String(30))
    response_text: Mapped[Optional[str]] = mapped_column(Text)


class DistributionDelivery(Base):
    __tablename__ = "distribution_deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    publication_id: Mapped[int] = mapped_column(
        ForeignKey("schedule_publications.id"), nullable=False
    )
    group_id: Mapped[int] = mapped_column(
        ForeignKey("student_groups.id"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(40), nullable=False)
    recipient: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[DeliveryStatus] = mapped_column(
        Enum(
            DeliveryStatus,
            name="delivery_status",
            native_enum=True,
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        default=DeliveryStatus.pending,
        nullable=False,
    )
    artifact_path: Mapped[Optional[str]] = mapped_column(String(500))
    provider_response: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
