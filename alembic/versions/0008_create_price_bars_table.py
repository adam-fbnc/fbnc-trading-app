"""create price_bars table

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-31
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "price_bars",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("frequency_type", sa.String(), nullable=False),
        sa.Column("frequency", sa.Integer(), nullable=False),
        sa.Column("bar_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("high", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("low", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("close", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "symbol", "frequency_type", "frequency", "bar_timestamp",
            name="uq_price_bars_symbol_freq_ts"
        ),
    )
    op.create_index("ix_price_bars_symbol", "price_bars", ["symbol"])
    op.create_index("ix_price_bars_bar_timestamp", "price_bars", ["bar_timestamp"])
    op.create_index(
        "ix_price_bars_symbol_freq_ts",
        "price_bars",
        ["symbol", "frequency_type", "frequency", "bar_timestamp"],
    )


def downgrade() -> None:
    op.drop_index("ix_price_bars_symbol_freq_ts", table_name="price_bars")
    op.drop_index("ix_price_bars_bar_timestamp", table_name="price_bars")
    op.drop_index("ix_price_bars_symbol", table_name="price_bars")
    op.drop_table("price_bars")
