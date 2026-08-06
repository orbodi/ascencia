"""backoffice tables

Revision ID: 0003_backoffice
Revises: 0002_planned_minutes
Create Date: 2026-08-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_backoffice"
down_revision: Union[str, Sequence[str], None] = "0002_planned_minutes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "academic_levels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(40), nullable=False, unique=True),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("degree", sa.String(8), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("speciality", sa.String(120), nullable=True),
    )
    op.create_table(
        "admin_users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(80), nullable=False, unique=True),
        sa.Column("email", sa.String(180), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column(
            "role",
            sa.Enum("superadmin", "admin", "viewer", name="admin_role"),
            nullable=False,
            server_default="admin",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_table(
        "system_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(80), nullable=False, unique=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_by", sa.String(80), nullable=True),
    )
    op.add_column(
        "student_groups",
        sa.Column(
            "academic_level_id",
            sa.Integer(),
            sa.ForeignKey("academic_levels.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "teachers",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("teachers", "is_active")
    op.drop_column("student_groups", "academic_level_id")
    op.drop_table("system_config")
    op.drop_table("admin_users")
    op.drop_table("academic_levels")
    op.execute("DROP TYPE IF EXISTS admin_role")
