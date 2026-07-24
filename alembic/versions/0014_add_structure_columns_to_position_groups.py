"""add structure_key, source_order_id, auto_managed to position_groups

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-23
"""
from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("position_groups", sa.Column("structure_key", sa.String(), nullable=True))
    op.add_column("position_groups", sa.Column("source_order_id", sa.String(), nullable=True))
    op.add_column(
        "position_groups",
        sa.Column("auto_managed", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_index("ix_position_groups_structure_key", "position_groups", ["structure_key"])
    op.create_index("ix_position_groups_source_order_id", "position_groups", ["source_order_id"])
    op.create_index("ix_position_groups_auto_managed", "position_groups", ["auto_managed"])


def downgrade() -> None:
    op.drop_index("ix_position_groups_auto_managed", table_name="position_groups")
    op.drop_index("ix_position_groups_source_order_id", table_name="position_groups")
    op.drop_index("ix_position_groups_structure_key", table_name="position_groups")
    op.drop_column("position_groups", "auto_managed")
    op.drop_column("position_groups", "source_order_id")
    op.drop_column("position_groups", "structure_key")
