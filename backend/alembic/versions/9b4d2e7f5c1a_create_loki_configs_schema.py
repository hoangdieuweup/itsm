"""create_loki_configs_schema

Revision ID: 9b4d2e7f5c1a
Revises: f3a8c1d9e4b7
Create Date: 2026-08-23 00:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = '9b4d2e7f5c1a'
down_revision = 'f3a8c1d9e4b7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('loki_configs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('environment_id', sa.UUID(), nullable=False),
    sa.Column('endpoint_url', sa.Text(), nullable=False),
    sa.Column('tenant_id', sa.String(length=128), nullable=True),
    sa.Column(
        'auth_type',
        sa.Enum('none', 'basic', 'bearer', name='lokiauthtype', native_enum=False),
        nullable=False,
    ),
    sa.Column('credential', sa.Text(), nullable=True),
    sa.Column('default_query', sa.Text(), nullable=False, server_default=''),
    sa.Column('default_range_minutes', sa.Integer(), nullable=False, server_default='60'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(
        ['environment_id'], ['environments.id'], name=op.f('loki_configs_environment_id_fkey'),
        ondelete='CASCADE'
    ),
    sa.PrimaryKeyConstraint('id', name=op.f('loki_configs_pkey')),
    sa.UniqueConstraint('environment_id', name=op.f('loki_configs_environment_id_key'))
    )


def downgrade() -> None:
    op.drop_table('loki_configs')
