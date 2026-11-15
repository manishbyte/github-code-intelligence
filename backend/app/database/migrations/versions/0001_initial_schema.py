"""Initial schema.

Creates every table from the models as they exist at the first release.
All later schema changes MUST be new revisions; never edit this file.

Revision ID: 0001
Revises:
"""

from __future__ import annotations

from alembic import op

from app.database.metadata import metadata

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    metadata.drop_all(bind=op.get_bind())
