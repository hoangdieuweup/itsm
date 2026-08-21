"""create_projects_schema

Revision ID: b6dd7c2f4a91
Revises: 4ecb44cf310b
Create Date: 2026-08-21 21:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'b6dd7c2f4a91'
down_revision = '4ecb44cf310b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('projects',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('projects_created_by_fkey'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('projects_pkey'))
    )
    op.create_table('project_links',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('project_id', sa.UUID(), nullable=False),
    sa.Column('type', sa.Enum('JIRA', 'GIT', 'OTHER', name='projectlinktype', native_enum=False), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('url', sa.Text(), nullable=False),
    sa.Column('is_default', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('project_links_project_id_fkey'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('project_links_pkey'))
    )
    op.create_index(op.f('project_links_project_id_idx'), 'project_links', ['project_id'], unique=False)
    op.create_table('environments',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('project_id', sa.UUID(), nullable=False),
    sa.Column('type', sa.Enum('DEV', 'STAGING', 'PRODUCTION', name='environmenttype', native_enum=False), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('base_url', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('environments_project_id_fkey'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('environments_pkey')),
    sa.UniqueConstraint('project_id', 'type', name='environments_project_id_type_key')
    )
    op.create_index(op.f('environments_project_id_idx'), 'environments', ['project_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('environments_project_id_idx'), table_name='environments')
    op.drop_table('environments')
    op.drop_index(op.f('project_links_project_id_idx'), table_name='project_links')
    op.drop_table('project_links')
    op.drop_table('projects')
