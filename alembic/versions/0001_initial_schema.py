"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-31
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "teachers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("email", sa.String(180), nullable=False, unique=True),
        sa.Column("phone_whatsapp", sa.String(32), nullable=True),
    )
    op.create_table(
        "student_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False, unique=True),
        sa.Column("whatsapp_group_id", sa.String(64), nullable=True),
        sa.Column("student_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "rooms",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False, unique=True),
        sa.Column("capacity", sa.Integer(), nullable=False, server_default="30"),
    )
    op.create_table(
        "time_slots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("day_of_week", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("label", sa.String(40), nullable=False),
        sa.UniqueConstraint(
            "day_of_week", "start_time", "end_time", name="uq_timeslot_day_hours"
        ),
    )
    op.create_table(
        "courses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("teacher_id", sa.Integer(), sa.ForeignKey("teachers.id"), nullable=False),
        sa.Column(
            "group_id", sa.Integer(), sa.ForeignKey("student_groups.id"), nullable=False
        ),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="120"),
    )
    op.create_table(
        "schedule_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("course_id", sa.Integer(), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("room_id", sa.Integer(), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column(
            "timeslot_id", sa.Integer(), sa.ForeignKey("time_slots.id"), nullable=False
        ),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("scheduled", "cancelled", "moved", name="schedule_entry_status"),
            nullable=False,
            server_default="scheduled",
        ),
        sa.UniqueConstraint(
            "room_id", "timeslot_id", "entry_date", name="uq_room_slot_date"
        ),
    )
    op.create_table(
        "availabilities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("teacher_id", sa.Integer(), sa.ForeignKey("teachers.id"), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("is_blocking", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "schedule_changes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "entry_id",
            sa.Integer(),
            sa.ForeignKey("schedule_entries.id"),
            nullable=False,
        ),
        sa.Column("before_json", sa.JSON(), nullable=False),
        sa.Column("after_json", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "proposed",
                "approved",
                "rejected",
                "applied",
                name="schedule_change_status",
            ),
            nullable=False,
            server_default="proposed",
        ),
        sa.Column("proposed_by", sa.String(80), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "conversation_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("channel", sa.String(40), nullable=False),
        sa.Column("external_user_id", sa.String(80), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("conversation_history")
    op.drop_table("schedule_changes")
    op.drop_table("availabilities")
    op.drop_table("schedule_entries")
    op.drop_table("courses")
    op.drop_table("time_slots")
    op.drop_table("rooms")
    op.drop_table("student_groups")
    op.drop_table("teachers")
    op.execute("DROP TYPE IF EXISTS schedule_change_status")
    op.execute("DROP TYPE IF EXISTS schedule_entry_status")
