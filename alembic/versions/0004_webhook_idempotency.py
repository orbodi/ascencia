"""whatsapp webhook idempotency

Revision ID: 0004_webhook_idempotency
Revises: 0003_backoffice
Create Date: 2026-08-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_webhook_idempotency"
down_revision: Union[str, Sequence[str], None] = "0003_backoffice"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "processed_inbound_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("channel", sa.String(40), nullable=False),
        sa.Column("message_id", sa.String(180), nullable=False, unique=True),
        sa.Column("sender_id", sa.String(80), nullable=False),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("processed_inbound_messages")
