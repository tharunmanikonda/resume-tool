"""track resume and generated PDF revisions

Revision ID: 20260721_0003
Revises: 20260720_0002
Create Date: 2026-07-21
"""

from alembic import op
import sqlalchemy as sa


revision = "20260721_0003"
down_revision = "20260720_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("resume_drafts")}
    if "resume_revision" not in columns:
        op.add_column("resume_drafts", sa.Column("resume_revision", sa.Integer(), nullable=False, server_default="1"))
    if "pdf_revision" not in columns:
        op.add_column("resume_drafts", sa.Column("pdf_revision", sa.Integer(), nullable=True))
    if "pdf_generated_at" not in columns:
        op.add_column("resume_drafts", sa.Column("pdf_generated_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        "UPDATE resume_drafts SET pdf_revision = resume_revision, pdf_generated_at = updated_at "
        "WHERE status IN ('pdf_ready', 'applied') AND pdf_stale = false AND pdf_path IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("resume_drafts", "pdf_generated_at")
    op.drop_column("resume_drafts", "pdf_revision")
    op.drop_column("resume_drafts", "resume_revision")
