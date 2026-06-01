"""create stream_events table

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-31
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stream_events",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stream_events_event_type", "stream_events", ["event_type"])
    op.create_index("ix_stream_events_received_at", "stream_events", ["received_at"])


def downgrade() -> None:
    op.drop_index("ix_stream_events_received_at", table_name="stream_events")
    op.drop_index("ix_stream_events_event_type", table_name="stream_events")
    op.drop_table("stream_events")
