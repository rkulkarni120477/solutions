"""Reusable private Word and PowerPoint templates."""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('proposal_templates',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('owner_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('filename', sa.String(220), nullable=False),
        sa.Column('kind', sa.String(10), nullable=False),
        sa.Column('key', sa.String(500), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False),
        sa.Column('archived', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_proposal_templates_owner_id', 'proposal_templates', ['owner_id'])


def downgrade():
    op.drop_table('proposal_templates')
