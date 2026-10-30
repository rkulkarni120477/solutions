"""Persist operational execution events without model or document content."""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('job_events',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('job_id', sa.String(36), sa.ForeignKey('jobs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('agent', sa.String(80), nullable=False),
        sa.Column('implementation', sa.String(160), nullable=False),
        sa.Column('agent_type', sa.String(30), nullable=False),
        sa.Column('stage', sa.String(40), nullable=False),
        sa.Column('kind', sa.String(50), nullable=False),
        sa.Column('message', sa.String(400), nullable=False),
        sa.Column('details', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_job_events_job_id', 'job_events', ['job_id'])


def downgrade():
    op.drop_table('job_events')
