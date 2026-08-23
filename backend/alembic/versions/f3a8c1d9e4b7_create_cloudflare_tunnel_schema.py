"""create_cloudflare_tunnel_schema

Revision ID: f3a8c1d9e4b7
Revises: d7e2a4c9f1b3
Create Date: 2026-08-23 09:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'f3a8c1d9e4b7'
down_revision = 'd7e2a4c9f1b3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('cloudflare_tunnels',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('environment_id', sa.UUID(), nullable=False),
    sa.Column('cf_tunnel_id', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column(
        'status',
        sa.Enum('healthy', 'degraded', 'down', 'unknown', name='cloudflaretunnelstatus', native_enum=False),
        nullable=False,
        server_default='unknown',
    ),
    sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(
        ['environment_id'], ['environments.id'], name=op.f('cloudflare_tunnels_environment_id_fkey'),
        ondelete='CASCADE'
    ),
    sa.PrimaryKeyConstraint('id', name=op.f('cloudflare_tunnels_pkey')),
    sa.UniqueConstraint('cf_tunnel_id', name=op.f('cloudflare_tunnels_cf_tunnel_id_key'))
    )
    op.create_index(
        op.f('cloudflare_tunnels_environment_id_idx'), 'cloudflare_tunnels', ['environment_id'], unique=False
    )
    op.create_table('tunnel_public_hostnames',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('tunnel_id', sa.UUID(), nullable=False),
    sa.Column('hostname', sa.String(length=255), nullable=False),
    sa.Column('service', sa.String(length=255), nullable=False),
    sa.Column(
        'managed_by',
        sa.Enum('system', 'external', name='tunnelhostnamemanagedby', native_enum=False),
        nullable=False,
        server_default='system',
    ),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(
        ['tunnel_id'], ['cloudflare_tunnels.id'], name=op.f('tunnel_public_hostnames_tunnel_id_fkey'),
        ondelete='CASCADE'
    ),
    sa.ForeignKeyConstraint(
        ['created_by'], ['users.id'], name=op.f('tunnel_public_hostnames_created_by_fkey'), ondelete='SET NULL'
    ),
    sa.PrimaryKeyConstraint('id', name=op.f('tunnel_public_hostnames_pkey')),
    sa.UniqueConstraint('hostname', name=op.f('tunnel_public_hostnames_hostname_key'))
    )
    op.create_index(
        op.f('tunnel_public_hostnames_tunnel_id_idx'), 'tunnel_public_hostnames', ['tunnel_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('tunnel_public_hostnames_tunnel_id_idx'), table_name='tunnel_public_hostnames')
    op.drop_table('tunnel_public_hostnames')
    op.drop_index(op.f('cloudflare_tunnels_environment_id_idx'), table_name='cloudflare_tunnels')
    op.drop_table('cloudflare_tunnels')
