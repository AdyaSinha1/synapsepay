"""initial schema: users, sessions, contracts, escrows, deliverables, evaluations, runs, events

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-11
"""
from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(64), nullable=False, server_default=""),
        sa.Column("role", sa.String(16), nullable=False, server_default="hirer"),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])

    op.create_table(
        "contracts",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("state", sa.String(24), nullable=False, server_default="FUNDED"),
        sa.Column("owner_id", sa.String(32), nullable=True),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_contracts_state", "contracts", ["state"])

    op.create_table(
        "escrows",
        sa.Column("contract_id", sa.String(32), primary_key=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="AUTHORIZED"),
        sa.Column("order_id", sa.String(64), nullable=True),
        sa.Column("authorization_id", sa.String(64), nullable=True),
        sa.Column("data", sa.JSON(), nullable=False),
    )
    op.create_index("ix_escrows_status", "escrows", ["status"])

    op.create_table(
        "deliverables",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("contract_id", sa.String(32), nullable=False),
        sa.Column("worker", sa.String(64), nullable=False, server_default="worker-agent-b"),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_deliverables_contract_id", "deliverables", ["contract_id"])

    op.create_table(
        "evaluations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("contract_id", sa.String(32), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False, server_default=""),
        sa.Column("composite", sa.Float(), nullable=False, server_default="0"),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_evaluations_contract_id", "evaluations", ["contract_id"])

    op.create_table(
        "runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("data", sa.JSON(), nullable=False),
    )

    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("contract_id", sa.String(32), nullable=True),
        sa.Column("stage", sa.String(40), nullable=False, server_default=""),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_events_contract_id", "events", ["contract_id"])


def downgrade() -> None:
    op.drop_table("events")
    op.drop_table("runs")
    op.drop_index("ix_evaluations_contract_id", table_name="evaluations")
    op.drop_table("evaluations")
    op.drop_index("ix_deliverables_contract_id", table_name="deliverables")
    op.drop_table("deliverables")
    op.drop_index("ix_escrows_status", table_name="escrows")
    op.drop_table("escrows")
    op.drop_index("ix_contracts_state", table_name="contracts")
    op.drop_table("contracts")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
