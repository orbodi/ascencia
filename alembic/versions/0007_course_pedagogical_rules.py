"""Course semester, priority and prerequisites.

Revision ID: 0007_course_pedagogical_rules
Revises: 0006_presence_distribution
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_course_pedagogical_rules"
down_revision = "0006_presence_distribution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("courses", sa.Column("semester", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("courses", sa.Column("priority", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("courses", sa.Column("prerequisite_course_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_courses_prerequisite_course_id_courses",
        "courses",
        "courses",
        ["prerequisite_course_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_courses_prerequisite_course_id_courses", "courses", type_="foreignkey")
    op.drop_column("courses", "prerequisite_course_id")
    op.drop_column("courses", "priority")
    op.drop_column("courses", "semester")
