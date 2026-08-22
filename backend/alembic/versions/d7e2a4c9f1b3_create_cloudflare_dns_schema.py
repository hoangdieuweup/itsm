"""create_cloudflare_dns_schema

Revision ID: d7e2a4c9f1b3
Revises: c1a3f9d2b8e4
Create Date: 2026-08-22 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'd7e2a4c9f1b3'
down_revision = 'c1a3f9d2b8e4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('cloudflare_configs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('environment_id', sa.UUID(), nullable=False),
    sa.Column('cloudflare_account_id', sa.UUID(), nullable=False),
    sa.Column('zone_id', sa.String(length=64), nullable=False),
    sa.Column('zone_name', sa.String(length=255), nullable=False),
    sa.Column(
        'log_source',
        sa.Enum('audit_log', 'logpush', 'graphql_analytics', name='cloudflarelogsource', native_enum=False),
        nullable=False,
        server_default='audit_log',
    ),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(
        ['environment_id'], ['environments.id'], name=op.f('cloudflare_configs_environment_id_fkey'),
        ondelete='CASCADE'
    ),
    sa.ForeignKeyConstraint(
        ['cloudflare_account_id'], ['cloudflare_accounts.id'],
        name=op.f('cloudflare_configs_cloudflare_account_id_fkey'), ondelete='RESTRICT'
    ),
    sa.PrimaryKeyConstraint('id', name=op.f('cloudflare_configs_pkey')),
    sa.UniqueConstraint('environment_id', name=op.f('cloudflare_configs_environment_id_key'))
    )
    op.create_table('dns_records',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('environment_id', sa.UUID(), nullable=False),
    sa.Column('cf_record_id', sa.String(length=64), nullable=False),
    sa.Column(
        'record_type',
        sa.Enum('A', 'AAAA', 'CNAME', 'TXT', 'MX', 'OTHER', name='dnsrecordtype', native_enum=False),
        nullable=False,
    ),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('priority', sa.Integer(), nullable=True),
    sa.Column('proxied', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    sa.Column('ttl', sa.Integer(), nullable=False, server_default='1'),
    sa.Column(
        'managed_by',
        sa.Enum('system', 'external', name='dnsrecordmanagedby', native_enum=False),
        nullable=False,
        server_default='system',
    ),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(
        ['environment_id'], ['environments.id'], name=op.f('dns_records_environment_id_fkey'), ondelete='CASCADE'
    ),
    sa.ForeignKeyConstraint(
        ['created_by'], ['users.id'], name=op.f('dns_records_created_by_fkey'), ondelete='SET NULL'
    ),
    sa.PrimaryKeyConstraint('id', name=op.f('dns_records_pkey')),
    sa.UniqueConstraint('cf_record_id', name=op.f('dns_records_cf_record_id_key'))
    )
    op.create_index(op.f('dns_records_environment_id_idx'), 'dns_records', ['environment_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('dns_records_environment_id_idx'), table_name='dns_records')
    op.drop_table('dns_records')
    op.drop_table('cloudflare_configs')
