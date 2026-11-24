"""subjects, semesters, exam attempts and mock exams

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-24 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "subjects",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("earliest_semester", sa.String(length=16), nullable=False),
        sa.Column("recommended_semester", sa.Integer(), nullable=True),
        sa.Column("not_before", sa.Date(), nullable=True),
        sa.Column("pass_mark", sa.Integer(), server_default="50", nullable=False),
        sa.Column(
            "sittings", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "semesters",
        sa.Column("label", sa.String(length=16), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint("label"),
    )
    op.create_table(
        "exam_attempts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("sitting", sa.Date(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "planned",
                "registered",
                "passed",
                "failed",
                name="attemptstatus",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_exam_attempts_subject_id", "exam_attempts", ["subject_id"])
    op.create_table(
        "mock_exams",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("entries", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("pass_mark", sa.Integer(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mock_exams_subject_id", "mock_exams", ["subject_id"])
    for table in ("modules", "runs"):
        op.add_column(table, sa.Column("subject_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            f"{table}_subject_id_fkey",
            table,
            "subjects",
            ["subject_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index(f"ix_{table}_subject_id", table, ["subject_id"])


def downgrade() -> None:
    for table in ("runs", "modules"):
        op.drop_index(f"ix_{table}_subject_id", table_name=table)
        op.drop_constraint(f"{table}_subject_id_fkey", table, type_="foreignkey")
        op.drop_column(table, "subject_id")
    op.drop_index("ix_mock_exams_subject_id", table_name="mock_exams")
    op.drop_table("mock_exams")
    op.drop_index("ix_exam_attempts_subject_id", table_name="exam_attempts")
    op.drop_table("exam_attempts")
    op.drop_table("semesters")
    op.drop_table("subjects")
