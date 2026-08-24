"""create_alerting_incidents_schema

Revision ID: 74b02f041f53
Revises: 7e2d9a4c8b1f
Create Date: 2026-08-24 00:00:00.000000
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "74b02f041f53"
down_revision = "7e2d9a4c8b1f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cloudflare_accounts", sa.Column("cf_webhook_destination_id", sa.String(length=64), nullable=True)
    )
    op.add_column("cloudflare_accounts", sa.Column("webhook_secret_ciphertext", sa.Text(), nullable=True))

    op.create_table(
        "alert_rules",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("environment_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "source",
            sa.Enum("CLOUDFLARE_NATIVE", "LOKI_QUERY", name="alertrulesource", native_enum=False),
            nullable=False,
        ),
        sa.Column("cf_alert_type", sa.String(length=100), nullable=True),
        sa.Column("cf_policy_id", sa.String(length=64), nullable=True),
        sa.Column("condition", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "severity",
            sa.Enum("LOW", "MEDIUM", "HIGH", "CRITICAL", name="alertseverity", native_enum=False),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["environment_id"],
            ["environments.id"],
            name=op.f("alert_rules_environment_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("alert_rules_pkey")),
    )
    op.create_index(op.f("alert_rules_environment_id_idx"), "alert_rules", ["environment_id"], unique=False)
    op.create_index(op.f("alert_rules_cf_policy_id_idx"), "alert_rules", ["cf_policy_id"], unique=False)

    op.create_table(
        "alert_rule_channels",
        sa.Column("alert_rule_id", sa.UUID(), nullable=False),
        sa.Column("channel_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["alert_rule_id"],
            ["alert_rules.id"],
            name=op.f("alert_rule_channels_alert_rule_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["channel_id"],
            ["notification_channels.id"],
            name=op.f("alert_rule_channels_channel_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("alert_rule_id", "channel_id", name=op.f("alert_rule_channels_pkey")),
    )

    op.create_table(
        "incidents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("environment_id", sa.UUID(), nullable=False),
        sa.Column("alert_rule_id", sa.UUID(), nullable=True),
        sa.Column(
            "source",
            sa.Enum("CLOUDFLARE", "LOKI", "MANUAL", name="incidentsource", native_enum=False),
            nullable=False,
        ),
        sa.Column(
            "category",
            sa.Enum(
                "TRAFFIC",
                "DDOS",
                "ORIGIN_ERROR",
                "DNS_DRIFT",
                "TUNNEL_DRIFT",
                "LOG_MATCH",
                "MANUAL",
                name="incidentcategory",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "severity",
            sa.Enum("LOW", "MEDIUM", "HIGH", "CRITICAL", name="alertseverity", native_enum=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("OPEN", "ACKNOWLEDGED", "RESOLVED", name="incidentstatus", native_enum=False),
            nullable=False,
            server_default="OPEN",
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("log_ref_id", sa.String(length=64), nullable=True),
        sa.Column("alert_correlation_id", sa.String(length=64), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", sa.UUID(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("incidents_project_id_fkey"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["environment_id"],
            ["environments.id"],
            name=op.f("incidents_environment_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["alert_rule_id"],
            ["alert_rules.id"],
            name=op.f("incidents_alert_rule_id_fkey"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["acknowledged_by"],
            ["users.id"],
            name=op.f("incidents_acknowledged_by_fkey"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by"], ["users.id"], name=op.f("incidents_resolved_by_fkey"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("incidents_pkey")),
    )
    op.create_index(op.f("incidents_project_id_idx"), "incidents", ["project_id"], unique=False)
    op.create_index(op.f("incidents_environment_id_idx"), "incidents", ["environment_id"], unique=False)
    op.create_index(
        op.f("incidents_alert_correlation_id_idx"), "incidents", ["alert_correlation_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("incidents_alert_correlation_id_idx"), table_name="incidents")
    op.drop_index(op.f("incidents_environment_id_idx"), table_name="incidents")
    op.drop_index(op.f("incidents_project_id_idx"), table_name="incidents")
    op.drop_table("incidents")
    op.drop_table("alert_rule_channels")
    op.drop_index(op.f("alert_rules_cf_policy_id_idx"), table_name="alert_rules")
    op.drop_index(op.f("alert_rules_environment_id_idx"), table_name="alert_rules")
    op.drop_table("alert_rules")
    op.drop_column("cloudflare_accounts", "webhook_secret_ciphertext")
    op.drop_column("cloudflare_accounts", "cf_webhook_destination_id")
