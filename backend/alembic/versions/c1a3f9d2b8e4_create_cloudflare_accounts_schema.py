"""create_cloudflare_accounts_schema

Revision ID: c1a3f9d2b8e4
Revises: b6dd7c2f4a91
Create Date: 2026-08-22 10:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'c1a3f9d2b8e4'
down_revision = 'b6dd7c2f4a91'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('cloudflare_accounts',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('label', sa.String(length=255), nullable=False),
    sa.Column('cf_account_id', sa.String(length=64), nullable=False),
    sa.Column('api_token', sa.Text(), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(
        ['created_by'], ['users.id'], name=op.f('cloudflare_accounts_created_by_fkey'), ondelete='SET NULL'
    ),
    sa.PrimaryKeyConstraint('id', name=op.f('cloudflare_accounts_pkey'))
    )
    op.create_table('cloudflare_account_managers',
    sa.Column('cloudflare_account_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column(
        'access_level',
        sa.Enum('owner', 'editor', 'viewer', name='cloudflareaccessLevel', native_enum=False),
        nullable=False,
    ),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(
        ['cloudflare_account_id'], ['cloudflare_accounts.id'],
        name=op.f('cloudflare_account_managers_cloudflare_account_id_fkey'), ondelete='CASCADE'
    ),
    sa.ForeignKeyConstraint(
        ['user_id'], ['users.id'], name=op.f('cloudflare_account_managers_user_id_fkey'), ondelete='CASCADE'
    ),
    sa.PrimaryKeyConstraint('cloudflare_account_id', 'user_id', name=op.f('cloudflare_account_managers_pkey'))
    )
    op.create_index(
        op.f('cloudflare_account_managers_user_id_idx'), 'cloudflare_account_managers', ['user_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('cloudflare_account_managers_user_id_idx'), table_name='cloudflare_account_managers')
    op.drop_table('cloudflare_account_managers')
    op.drop_table('cloudflare_accounts')
