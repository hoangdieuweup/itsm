"""fix_dns_record_environment_scoping

Revision ID: 8a79eab65342
Revises: a2f7c391e05d
Create Date: 2026-08-24 23:00:00.000000

Same class of bug as a2f7c391e05d (Tunnel environment scoping), never
fixed for DNS records. `cloudflare_configs.zone_id` is not unique across
environments — many environments can independently bind to the same
shared Cloudflare zone. `SyncDnsRecords` fetched every record in that
zone with no per-record matching against which environment it actually
belongs to, so whichever environment happened to sync a shared zone
first permanently claimed every record in it (via
`dns_records.environment_id` being NOT NULL, forcing an attribution even
when none was known), including records with nothing to do with it.
`UpdateDnsRecord`/`DeleteDnsRecord`'s ownership check
(`existing.environment_id != environment_id`) was therefore vacuous for
zone-shared records — this is what let one project's users edit/delete
another service's live DNS records.

This migration only relaxes the column's NOT NULL constraint —
`dns_records.environment_id` becomes nullable, mirroring
`tunnel_public_hostnames.environment_id`'s exact treatment in the Tunnel
fix. No data backfill: historical mis-attribution is unrecoverable (the
information about which environment a shared-zone record "should" belong
to was already lost), but the very next sync against each environment
now correctly re-matches every record against sibling environments'
`base_url` (`app/modules/cloudflare/services/sync_dns_records.py`),
self-healing forward. FK stays ON DELETE CASCADE — a record whose owning
environment is deleted has no reason to persist, unchanged from before.
"""

import sqlalchemy as sa

from alembic import op

revision = "8a79eab65342"
down_revision = "a2f7c391e05d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("dns_records", "environment_id", existing_type=sa.UUID(), nullable=True)


def downgrade() -> None:
    # Any row that synced to environment_id=None under the new logic would
    # violate a reinstated NOT NULL — dev-convenience downgrade only, never
    # intended as a real rollback path once unmatched rows exist in itsm_test.
    op.alter_column("dns_records", "environment_id", existing_type=sa.UUID(), nullable=False)
