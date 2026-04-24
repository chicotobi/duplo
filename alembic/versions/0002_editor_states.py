"""Add editor_states table for server-side editor autosave.

Revision ID: 0002_editor_states
Revises: 0001_baseline
Create Date: 2026-04-24
"""
from alembic import op
import sqlalchemy as sa


revision = "0002_editor_states"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "editor_states",
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "track_id",
            sa.Integer,
            sa.ForeignKey("tracks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("pieces_json", sa.Text, nullable=False),
        sa.Column("connections_json", sa.Text, nullable=False),
        sa.Column("cursor_idx", sa.Integer, nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.PrimaryKeyConstraint("user_id", "track_id"),
    )


def downgrade() -> None:
    op.drop_table("editor_states")
