"""Baseline schema: users, tracks, pieces, connections.

Captures the schema the app was running with prior to introducing Alembic.
Cross-dialect (sqlite + mysql) by using SQLAlchemy types and constraints.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-04-24
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
        sa.Column("idx", sa.Integer, nullable=False),
        sa.Column("piece", sa.String(10), nullable=False),
    )
    op.create_table(
        "connections",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "track_id",
            sa.Integer,
            sa.ForeignKey("tracks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("p1", sa.Integer, nullable=False),
        sa.Column("e1", sa.Integer, nullable=False),
        sa.Column("p2", sa.Integer, nullable=False),
        sa.Column("e2", sa.Integer, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("connections")
    op.drop_table("pieces")
    op.drop_table("tracks")
    op.drop_table("users")
