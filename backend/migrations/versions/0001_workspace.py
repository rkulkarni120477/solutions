"""Initial workspace schema, frozen independently of application models."""
from alembic import op
import sqlalchemy as sa
revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('users', sa.Column('id',sa.String(36),primary_key=True), sa.Column('subject',sa.String(700),nullable=False,unique=True), sa.Column('name',sa.String(200),nullable=False))
    op.create_table('projects',sa.Column('id',sa.String(36),primary_key=True),sa.Column('owner_id',sa.String(36),sa.ForeignKey('users.id'),nullable=False),sa.Column('title',sa.String(160),nullable=False),sa.Column('decisions',sa.JSON(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_projects_owner_id','projects',['owner_id'])
    op.create_table('versions',sa.Column('id',sa.String(36),primary_key=True),sa.Column('project_id',sa.String(36),sa.ForeignKey('projects.id',ondelete='CASCADE'),nullable=False),sa.Column('number',sa.Integer(),nullable=False),sa.Column('prompt',sa.Text(),nullable=False),sa.Column('preferences',sa.JSON(),nullable=False),sa.Column('response',sa.JSON(),nullable=True),sa.Column('context_sources',sa.JSON(),nullable=False),sa.Column('provider',sa.String(30),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.UniqueConstraint('project_id','number'))
    op.create_index('ix_versions_project_id','versions',['project_id'])
    op.create_table('attachments',sa.Column('id',sa.String(36),primary_key=True),sa.Column('project_id',sa.String(36),sa.ForeignKey('projects.id',ondelete='CASCADE'),nullable=False),sa.Column('filename',sa.String(220),nullable=False),sa.Column('key',sa.String(500),nullable=False),sa.Column('size',sa.Integer(),nullable=False),sa.Column('passages',sa.JSON(),nullable=False),sa.Column('warning',sa.Text(),nullable=True))
    op.create_index('ix_attachments_project_id','attachments',['project_id'])
    op.create_table('jobs',sa.Column('id',sa.String(36),primary_key=True),sa.Column('project_id',sa.String(36),sa.ForeignKey('projects.id',ondelete='CASCADE'),nullable=False),sa.Column('version_id',sa.String(36),sa.ForeignKey('versions.id',ondelete='CASCADE'),nullable=False),sa.Column('status',sa.String(40),nullable=False),sa.Column('kind',sa.String(40),nullable=False),sa.Column('artifact_id',sa.String(36),nullable=True),sa.Column('error',sa.Text(),nullable=True),sa.Column('attempts',sa.Integer(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_jobs_project_id','jobs',['project_id'])
    op.create_index('ix_jobs_status','jobs',['status'])
    op.create_table('artifacts',sa.Column('id',sa.String(36),primary_key=True),sa.Column('project_id',sa.String(36),sa.ForeignKey('projects.id',ondelete='CASCADE'),nullable=False),sa.Column('version_id',sa.String(36),sa.ForeignKey('versions.id',ondelete='CASCADE'),nullable=False),sa.Column('kind',sa.String(40),nullable=False),sa.Column('filename',sa.String(200),nullable=False),sa.Column('status',sa.String(30),nullable=False),sa.Column('key',sa.String(500),nullable=True),sa.Column('error',sa.Text(),nullable=True))
    op.create_index('ix_artifacts_project_id','artifacts',['project_id'])
    op.create_index('ix_artifacts_version_id','artifacts',['version_id'])
    op.create_table('audit_events',sa.Column('id',sa.String(36),primary_key=True),sa.Column('user_id',sa.String(36),nullable=False),sa.Column('action',sa.String(80),nullable=False),sa.Column('resource_id',sa.String(36),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_audit_events_user_id','audit_events',['user_id'])


def downgrade():
    for table in ['audit_events','artifacts','jobs','attachments','versions','projects','users']:
        op.drop_table(table)
