"""add persistent resume extension drafts

Revision ID: 20260720_0002
Revises:
Create Date: 2026-07-20
"""

from alembic import op

from database import ResumeDraft, ResumeDraftTask

revision = "20260720_0002"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    ResumeDraft.__table__.create(bind=bind, checkfirst=True)
    ResumeDraftTask.__table__.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    ResumeDraftTask.__table__.drop(bind=bind, checkfirst=True)
    ResumeDraft.__table__.drop(bind=bind, checkfirst=True)
