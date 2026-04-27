"""Add room_w and room_h columns to users.

Revision ID: 0002_room_size
Revises: 0001_baseline
Create Date: 2026-04-27
"""
from alembic import op
import sqlalchemy as sa


revision = "0002_room_size"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("room_w", sa.Integer, nullable=False, server_default="6"))
    op.add_column("users", sa.Column("room_h", sa.Integer, nullable=False, server_default="4"))


def downgrade() -> None:
    op.drop_column("users", "room_h")
    op.drop_column("users", "room_w")
