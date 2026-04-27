"""Baseline schema: users, tracks, pieces, editor_states.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-04-27
"""
from alembic import op
import sqlalchemy as sa


revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("hash", sa.Text, nullable=False),
        sa.Column("straight", sa.Integer),
        sa.Column("curve", sa.Integer),
        sa.Column("switch", sa.Integer),
        sa.Column("crossing", sa.Integer),
    )
    op.create_table(
        "tracks",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.Text, nullable=False),
    )
    op.create_table(
        "pieces",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "track_id",
            sa.Integer,
            sa.ForeignKey("tracks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("piece", sa.String(10), nullable=False),
        sa.Column("x", sa.Float, nullable=False, server_default="0"),
        sa.Column("y", sa.Float, nullable=False, server_default="0"),
        sa.Column("rot", sa.Integer, nullable=False, server_default="0"),
    )
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
        sa.Column("selection_json", sa.Text, nullable=True),
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
    op.drop_table("pieces")
    op.drop_table("tracks")
    op.drop_table("users")
