"""chapter status skipped

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-24 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD = ("pending", "generating", "verifying", "ready", "failed")
_NEW = (*_OLD, "skipped")


def _status(values: tuple[str, ...]) -> sa.Enum:
    return sa.Enum(*values, name="chapterstatus", native_enum=False, length=32)


def upgrade() -> None:
    op.alter_column(
        "chapters",
        "status",
        type_=_status(_NEW),
        existing_type=_status(_OLD),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.execute("UPDATE chapters SET status = 'failed' WHERE status = 'skipped'")
    op.alter_column(
        "chapters",
        "status",
        type_=_status(_OLD),
        existing_type=_status(_NEW),
        existing_nullable=False,
    )
