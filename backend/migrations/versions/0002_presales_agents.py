"""Presales multi-agent proposals, agent messages and published response documents."""
from alembic import op
import sqlalchemy as sa
revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('proposals',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('request', sa.Text(), nullable=False),
        sa.Column('formats', sa.JSON(), nullable=False),
        sa.Column('preferences', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(40), nullable=False),
        sa.Column('requirements', sa.JSON(), nullable=True),
        sa.Column('answers', sa.JSON(), nullable=False),
        sa.Column('assumptions_accepted', sa.Boolean(), nullable=False),
        sa.Column('plan', sa.JSON(), nullable=True),
        sa.Column('draft_version_id', sa.String(36), sa.ForeignKey('versions.id', ondelete='SET NULL'), nullable=True),
        sa.Column('reviews', sa.JSON(), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('approved_by', sa.String(36), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_proposals_project_id', 'proposals', ['project_id'])
    op.create_table('agent_messages',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('proposal_id', sa.String(36), sa.ForeignKey('proposals.id', ondelete='CASCADE'), nullable=False),
        sa.Column('agent', sa.String(60), nullable=False),
        sa.Column('recipient', sa.String(60), nullable=True),
        sa.Column('kind', sa.String(30), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_agent_messages_proposal_id', 'agent_messages', ['proposal_id'])
    op.create_table('response_documents',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('proposal_id', sa.String(36), sa.ForeignKey('proposals.id', ondelete='CASCADE'), nullable=False),
        sa.Column('version_id', sa.String(36), nullable=False),
        sa.Column('kind', sa.String(40), nullable=False),
        sa.Column('filename', sa.String(200), nullable=False),
        sa.Column('key', sa.String(500), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_response_documents_project_id', 'response_documents', ['project_id'])
    op.create_index('ix_response_documents_proposal_id', 'response_documents', ['proposal_id'])
    with op.batch_alter_table('jobs') as batch:
        batch.alter_column('version_id', existing_type=sa.String(36), nullable=True)
        batch.add_column(sa.Column('proposal_id', sa.String(36), nullable=True))
        batch.create_foreign_key('fk_jobs_proposal_id_proposals', 'proposals', ['proposal_id'], ['id'], ondelete='CASCADE')
        batch.create_index('ix_jobs_proposal_id', ['proposal_id'])


def downgrade():
    op.execute('DELETE FROM jobs WHERE proposal_id IS NOT NULL OR version_id IS NULL')
    with op.batch_alter_table('jobs') as batch:
        batch.drop_index('ix_jobs_proposal_id')
        batch.drop_constraint('fk_jobs_proposal_id_proposals', type_='foreignkey')
        batch.drop_column('proposal_id')
        batch.alter_column('version_id', existing_type=sa.String(36), nullable=False)
    op.drop_table('response_documents')
    op.drop_table('agent_messages')
    op.drop_table('proposals')
