"""Add forced_connections JSON column to tracks.

Revision ID: 0003_forced_connections
Revises: 0002_room_size
Create Date: 2026-05-04
"""
from alembic import op
import sqlalchemy as sa


revision = "0003_forced_connections"
down_revision = "0002_room_size"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('tracks', sa.Column('forced_connections', sa.Text(), server_default='[]'))


def downgrade() -> None:
    op.drop_column('tracks', 'forced_connections')
