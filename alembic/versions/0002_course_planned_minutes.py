"""add course planned_minutes

Revision ID: 0002_planned_minutes
Revises: 0001_initial
Create Date: 2026-07-31
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_planned_minutes"
down_revision: Union[str, Sequence[str], None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "courses",
        sa.Column(
            "planned_minutes",
            sa.Integer(),
            nullable=False,
            server_default="720",
        ),
    )


def downgrade() -> None:
    op.drop_column("courses", "planned_minutes")
