"""Curriculum multi-week plans per academic level.

Revision ID: 0008_curriculum_plans
Revises: 0007_course_pedagogical_rules
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_curriculum_plans"
down_revision = "0007_course_pedagogical_rules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "curriculum_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("academic_level_id", sa.Integer(), nullable=False),
        sa.Column("semester", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("week_count", sa.Integer(), nullable=False, server_default="6"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["academic_level_id"],
            ["academic_levels.id"],
            name="fk_curriculum_plans_academic_level_id",
        ),
        sa.UniqueConstraint(
            "academic_level_id",
            "semester",
            name="uq_curriculum_plan_level_semester",
        ),
    )
    op.create_table(
        "curriculum_week_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("week_index", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("sessions_count", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["curriculum_plans.id"],
            name="fk_curriculum_week_items_plan_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name="fk_curriculum_week_items_course_id",
        ),
        sa.UniqueConstraint(
            "plan_id",
            "week_index",
            "course_id",
            name="uq_curriculum_week_course",
        ),
    )


def downgrade() -> None:
    op.drop_table("curriculum_week_items")
    op.drop_table("curriculum_plans")
