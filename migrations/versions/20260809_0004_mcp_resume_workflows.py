"""add MCP resume workflow state

Revision ID: 20260809_0004
Revises: 20260721_0003
Create Date: 2026-08-09
"""

from alembic import op

from database import McpResumeWorkflow


revision = "20260809_0004"
down_revision = "20260721_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    McpResumeWorkflow.__table__.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    McpResumeWorkflow.__table__.drop(bind=op.get_bind(), checkfirst=True)
