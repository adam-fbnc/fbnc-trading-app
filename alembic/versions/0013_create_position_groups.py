"""create position_groups, position_group_legs, group_alerts tables

Revision ID: 0013
Revises: 0012
Create Date: 2026-06-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "position_groups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_hash", sa.String(), nullable=False),
        sa.Column("underlying", sa.String(), nullable=False),
        sa.Column("group_type", sa.String(), nullable=False),
        sa.Column("alias", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="OPEN"),
        sa.Column("entry_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_position_groups_account_hash", "position_groups", ["account_hash"])
    op.create_index("ix_position_groups_underlying", "position_groups", ["underlying"])
    op.create_index("ix_position_groups_status", "position_groups", ["status"])

    op.create_table(
        "position_group_legs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("underlying", sa.String(), nullable=False),
        sa.Column("contract_type", sa.String(), nullable=False),
        sa.Column("strike", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("expiration", sa.Date(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("entry_price", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["position_groups.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_position_group_legs_group_id", "position_group_legs", ["group_id"])
    op.create_index("ix_position_group_legs_symbol", "position_group_legs", ["symbol"])

    op.create_table(
        "group_alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("alert_type", sa.String(), nullable=False),
        sa.Column("threshold_pct", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["group_id"], ["position_groups.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_group_alerts_group_id", "group_alerts", ["group_id"])


def downgrade() -> None:
    op.drop_index("ix_group_alerts_group_id", table_name="group_alerts")
    op.drop_table("group_alerts")

    op.drop_index("ix_position_group_legs_symbol", table_name="position_group_legs")
    op.drop_index("ix_position_group_legs_group_id", table_name="position_group_legs")
    op.drop_table("position_group_legs")

    op.drop_index("ix_position_groups_status", table_name="position_groups")
    op.drop_index("ix_position_groups_underlying", table_name="position_groups")
    op.drop_index("ix_position_groups_account_hash", table_name="position_groups")
    op.drop_table("position_groups")
