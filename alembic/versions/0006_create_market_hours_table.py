"""create market_hours table

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-31
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_hours",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("market", sa.String(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("is_open", sa.Boolean(), nullable=False),
        sa.Column("session_hours", JSONB(), nullable=True),
        sa.Column("raw", JSONB(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("market", "date", name="uq_market_hours_market_date"),
    )
    op.create_index("ix_market_hours_market", "market_hours", ["market"])
    op.create_index("ix_market_hours_date", "market_hours", ["date"])


def downgrade() -> None:
    op.drop_index("ix_market_hours_date", table_name="market_hours")
    op.drop_index("ix_market_hours_market", table_name="market_hours")
    op.drop_table("market_hours")
