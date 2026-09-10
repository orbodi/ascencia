"""presence confirmation campaigns and distribution logs

Revision ID: 0006_presence_distribution
Revises: 0005_schedule_publications
Create Date: 2026-08-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_presence_distribution"
down_revision: Union[str, Sequence[str], None] = "0005_schedule_publications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    campaign_status = sa.Enum(
        "open", "ready", "requires_revision", "completed",
        name="presence_campaign_status",
    )
    response_status = sa.Enum(
        "pending", "confirmed", "unavailable", name="presence_response_status"
    )
    delivery_status = sa.Enum(
        "pending", "sent", "failed", "skipped", name="delivery_status"
    )
    op.add_column(
        "student_groups",
        sa.Column(
            "distribution_recipients",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )
    op.add_column(
        "schedule_publications", sa.Column("xlsx_path", sa.String(500), nullable=True)
    )
    op.create_table(
        "presence_campaigns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "publication_id",
            sa.Integer(),
            sa.ForeignKey("schedule_publications.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("status", campaign_status, nullable=False, server_default="open"),
        sa.Column("channels", sa.JSON(), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(80), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "presence_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "campaign_id", sa.Integer(), sa.ForeignKey("presence_campaigns.id"),
            nullable=False,
        ),
        sa.Column(
            "teacher_id", sa.Integer(), sa.ForeignKey("teachers.id"), nullable=False
        ),
        sa.Column("token", sa.String(80), nullable=False, unique=True),
        sa.Column("status", response_status, nullable=False, server_default="pending"),
        sa.Column("sent_channels", sa.JSON(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response_channel", sa.String(30), nullable=True),
        sa.Column("response_text", sa.Text(), nullable=True),
        sa.UniqueConstraint(
            "campaign_id", "teacher_id", name="uq_presence_campaign_teacher"
        ),
    )
    op.create_table(
        "distribution_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "publication_id", sa.Integer(),
            sa.ForeignKey("schedule_publications.id"), nullable=False,
        ),
        sa.Column(
            "group_id", sa.Integer(), sa.ForeignKey("student_groups.id"),
            nullable=False,
        ),
        sa.Column("channel", sa.String(40), nullable=False),
        sa.Column("recipient", sa.String(120), nullable=False),
        sa.Column("status", delivery_status, nullable=False, server_default="pending"),
        sa.Column("artifact_path", sa.String(500), nullable=True),
        sa.Column("provider_response", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("distribution_deliveries")
    op.drop_table("presence_requests")
    op.drop_table("presence_campaigns")
    op.drop_column("schedule_publications", "xlsx_path")
    op.drop_column("student_groups", "distribution_recipients")
    op.execute("DROP TYPE IF EXISTS delivery_status")
    op.execute("DROP TYPE IF EXISTS presence_response_status")
    op.execute("DROP TYPE IF EXISTS presence_campaign_status")
