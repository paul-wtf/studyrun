"""chapter waiting_since

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-23 23:40:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("chapters", sa.Column("waiting_since", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("chapters", "waiting_since")
