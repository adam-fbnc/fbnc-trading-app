"""create option_contracts table

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-31
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "option_contracts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("underlying_symbol", sa.String(), nullable=False),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("cusip", sa.String(), nullable=True),
        sa.Column("contract_type", sa.String(), nullable=False),
        sa.Column("expiration_date", sa.Date(), nullable=False),
        sa.Column("strike", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("open_interest", sa.Integer(), nullable=True),
        sa.Column("volume", sa.Integer(), nullable=True),
        sa.Column("implied_volatility", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("delta", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("gamma", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("theta", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("vega", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("last_price", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("bid", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("ask", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("raw", JSONB(), nullable=False),
        sa.Column("snapped_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "underlying_symbol", "expiration_date", "strike", "contract_type", "snapped_at",
            name="uq_option_contracts_key"
        ),
    )
    op.create_index("ix_option_contracts_underlying", "option_contracts", ["underlying_symbol"])
    op.create_index("ix_option_contracts_symbol", "option_contracts", ["symbol"])
    op.create_index("ix_option_contracts_cusip", "option_contracts", ["cusip"])
    op.create_index("ix_option_contracts_expiration", "option_contracts", ["expiration_date"])
    op.create_index("ix_option_contracts_strike", "option_contracts", ["strike"])
    op.create_index("ix_option_contracts_snapped_at", "option_contracts", ["snapped_at"])


def downgrade() -> None:
    op.drop_index("ix_option_contracts_snapped_at", table_name="option_contracts")
    op.drop_index("ix_option_contracts_strike", table_name="option_contracts")
    op.drop_index("ix_option_contracts_expiration", table_name="option_contracts")
    op.drop_index("ix_option_contracts_cusip", table_name="option_contracts")
    op.drop_index("ix_option_contracts_symbol", table_name="option_contracts")
    op.drop_index("ix_option_contracts_underlying", table_name="option_contracts")
    op.drop_table("option_contracts")
