"""schedule generation publications

Revision ID: 0005_schedule_publications
Revises: 0004_webhook_idempotency
Create Date: 2026-08-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_schedule_publications"
down_revision: Union[str, Sequence[str], None] = "0004_webhook_idempotency"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    publication_status = sa.Enum(
        "draft", "published", "archived", name="publication_status"
    )
    op.create_table(
        "schedule_publications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version_number", sa.String(60), nullable=False, unique=True),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("week_end", sa.Date(), nullable=False),
        sa.Column("status", publication_status, nullable=False, server_default="draft"),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column("generation_report", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(80), nullable=False),
        sa.Column("published_by", sa.String(80), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("schedule_publications")
    op.execute("DROP TYPE IF EXISTS publication_status")
