"""fix_tunnel_environment_scoping

Revision ID: a2f7c391e05d
Revises: 74b02f041f53
Create Date: 2026-08-24 09:00:00.000000

Cloudflare Tunnels are account-level resources that can serve many
environments at once (e.g. one tunnel routing hostnames for 4 different
projects). Modeling `cloudflare_tunnels.environment_id` as a single NOT
NULL FK was wrong, and combined with SyncTunnels upserting every account
tunnel onto whichever environment triggered the sync, it silently
reassigned every tunnel in an account to the last-visited environment on
every page load — see bugs/cloudflare-tunnel-ingress-and-project-environment-mapping.md.

This migration moves the scoping key from the tunnel row to the hostname
row: `cloudflare_tunnels` becomes account-scoped, and
`tunnel_public_hostnames` gains a nullable `environment_id` that the
(now account-wide) sync populates by matching each hostname against the
bound environments' `base_url`.

Historical `environment_id` values on `cloudflare_tunnels` are unrecoverable
as "which environment should this tunnel serve" — that information was
already lost by the bug this migration fixes. What IS backfillable is
which Cloudflare account each tunnel belongs to, via the (uncorrupted)
`cloudflare_configs` chain — the very next sync after this migration then
self-heals every environment's real hostname associations from Cloudflare's
own live state.
"""

import sqlalchemy as sa

from alembic import op

revision = "a2f7c391e05d"
down_revision = "74b02f041f53"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cloudflare_tunnels", sa.Column("cloudflare_account_id", sa.UUID(), nullable=True))
    op.execute(
        """
        UPDATE cloudflare_tunnels
        SET cloudflare_account_id = cloudflare_configs.cloudflare_account_id
        FROM cloudflare_configs
        WHERE cloudflare_configs.environment_id = cloudflare_tunnels.environment_id
        """
    )
    # A tunnel whose triggering environment no longer has a Cloudflare binding
    # has no account to backfill from — its account identity was already lost
    # by the bug this migration fixes. It cascades away here; the next sync
    # against the real Cloudflare account re-creates it correctly.
    op.execute("DELETE FROM cloudflare_tunnels WHERE cloudflare_account_id IS NULL")
    op.alter_column("cloudflare_tunnels", "cloudflare_account_id", nullable=False)

    op.drop_constraint(
        op.f("cloudflare_tunnels_environment_id_fkey"), "cloudflare_tunnels", type_="foreignkey"
    )
    op.drop_index(op.f("cloudflare_tunnels_environment_id_idx"), table_name="cloudflare_tunnels")
    op.drop_column("cloudflare_tunnels", "environment_id")

    op.create_index(
        op.f("cloudflare_tunnels_cloudflare_account_id_idx"),
        "cloudflare_tunnels",
        ["cloudflare_account_id"],
        unique=False,
    )
    op.create_foreign_key(
        op.f("cloudflare_tunnels_cloudflare_account_id_fkey"),
        "cloudflare_tunnels",
        "cloudflare_accounts",
        ["cloudflare_account_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.add_column("tunnel_public_hostnames", sa.Column("environment_id", sa.UUID(), nullable=True))
    op.create_index(
        op.f("tunnel_public_hostnames_environment_id_idx"),
        "tunnel_public_hostnames",
        ["environment_id"],
        unique=False,
    )
    op.create_foreign_key(
        op.f("tunnel_public_hostnames_environment_id_fkey"),
        "tunnel_public_hostnames",
        "environments",
        ["environment_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("tunnel_public_hostnames_environment_id_fkey"), "tunnel_public_hostnames", type_="foreignkey"
    )
    op.drop_index(op.f("tunnel_public_hostnames_environment_id_idx"), table_name="tunnel_public_hostnames")
    op.drop_column("tunnel_public_hostnames", "environment_id")

    op.drop_constraint(
        op.f("cloudflare_tunnels_cloudflare_account_id_fkey"), "cloudflare_tunnels", type_="foreignkey"
    )
    op.drop_index(op.f("cloudflare_tunnels_cloudflare_account_id_idx"), table_name="cloudflare_tunnels")

    # Historical tunnel->environment intent is unrecoverable (see module
    # docstring) — the column is restored nullable with no backfill, a
    # dev-convenience downgrade only, never intended for the corrupted data
    # this migration was written to fix.
    op.add_column("cloudflare_tunnels", sa.Column("environment_id", sa.UUID(), nullable=True))
    op.create_index(
        op.f("cloudflare_tunnels_environment_id_idx"), "cloudflare_tunnels", ["environment_id"], unique=False
    )
    op.create_foreign_key(
        op.f("cloudflare_tunnels_environment_id_fkey"),
        "cloudflare_tunnels",
        "environments",
        ["environment_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_column("cloudflare_tunnels", "cloudflare_account_id")
