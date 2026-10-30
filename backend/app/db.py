import uuid
from datetime import datetime, timezone
from sqlalchemy import create_engine, String, Text, JSON, ForeignKey, DateTime, Integer, Boolean, UniqueConstraint, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from .config import settings


def uid():
    return str(uuid.uuid4())


def now():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    subject: Mapped[str] = mapped_column(String(700), unique=True)
    name: Mapped[str] = mapped_column(String(200))


class Project(Base):
    __tablename__ = 'projects'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    title: Mapped[str] = mapped_column(String(160))
    decisions: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ProposalTemplate(Base):
    __tablename__ = 'proposal_templates'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    filename: Mapped[str] = mapped_column(String(220))
    kind: Mapped[str] = mapped_column(String(10))
    key: Mapped[str] = mapped_column(String(500))
    size: Mapped[int] = mapped_column(Integer)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Version(Base):
    __tablename__ = 'versions'
    __table_args__ = (UniqueConstraint('project_id', 'number'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id', ondelete='CASCADE'), index=True)
    number: Mapped[int] = mapped_column(Integer)
    prompt: Mapped[str] = mapped_column(Text)
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)
    response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    context_sources: Mapped[list] = mapped_column(JSON, default=list)
    provider: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Attachment(Base):
    __tablename__ = 'attachments'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id', ondelete='CASCADE'), index=True)
    filename: Mapped[str] = mapped_column(String(220))
    key: Mapped[str] = mapped_column(String(500))
    size: Mapped[int] = mapped_column(Integer)
    passages: Mapped[list] = mapped_column(JSON, default=list)
    warning: Mapped[str | None] = mapped_column(Text, nullable=True)


class Job(Base):
    __tablename__ = 'jobs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id', ondelete='CASCADE'), index=True)
    # Proposal requirement-collection jobs run before a draft version exists.
    version_id: Mapped[str | None] = mapped_column(ForeignKey('versions.id', ondelete='CASCADE'), nullable=True)
    proposal_id: Mapped[str | None] = mapped_column(ForeignKey('proposals.id', ondelete='CASCADE'), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), default='Queued', index=True)
    kind: Mapped[str] = mapped_column(String(40), default='solution')
    artifact_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Artifact(Base):
    __tablename__ = 'artifacts'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id', ondelete='CASCADE'), index=True)
    version_id: Mapped[str] = mapped_column(ForeignKey('versions.id', ondelete='CASCADE'), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    filename: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(30), default='Queued')
    key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class JobEvent(Base):
    __tablename__ = 'job_events'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    job_id: Mapped[str] = mapped_column(ForeignKey('jobs.id', ondelete='CASCADE'), index=True)
    agent: Mapped[str] = mapped_column(String(80))
    implementation: Mapped[str] = mapped_column(String(160))
    agent_type: Mapped[str] = mapped_column(String(30))
    stage: Mapped[str] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(50))
    message: Mapped[str] = mapped_column(String(400))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Proposal(Base):
    """Presales RFP response workflow, including the human approval gate."""
    __tablename__ = 'proposals'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id', ondelete='CASCADE'), index=True)
    request: Mapped[str] = mapped_column(Text)
    formats: Mapped[list] = mapped_column(JSON, default=list)
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(40), default='Queued')
    requirements: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    assumptions_accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    plan: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    draft_version_id: Mapped[str | None] = mapped_column(ForeignKey('versions.id', ondelete='SET NULL'), nullable=True)
    reviews: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AgentMessage(Base):
    __tablename__ = 'agent_messages'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    proposal_id: Mapped[str] = mapped_column(ForeignKey('proposals.id', ondelete='CASCADE'), index=True)
    agent: Mapped[str] = mapped_column(String(60))
    recipient: Mapped[str | None] = mapped_column(String(60), nullable=True)
    kind: Mapped[str] = mapped_column(String(30))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ResponseDocument(Base):
    """Immutable copy of an approved proposal deliverable."""
    __tablename__ = 'response_documents'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id', ondelete='CASCADE'), index=True)
    proposal_id: Mapped[str] = mapped_column(ForeignKey('proposals.id', ondelete='CASCADE'), index=True)
    version_id: Mapped[str] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(40))
    filename: Mapped[str] = mapped_column(String(200))
    key: Mapped[str] = mapped_column(String(500))
    size: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Audit(Base):
    __tablename__ = 'audit_events'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


engine = create_engine(settings.database_url, connect_args={'check_same_thread': False} if settings.database_url.startswith('sqlite') else {}, pool_pre_ping=True)
if settings.database_url.startswith('sqlite'):
    @event.listens_for(engine, 'connect')
    def sqlite_options(conn, _):
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('PRAGMA busy_timeout=10000')
Session = sessionmaker(engine, expire_on_commit=False)


def get_db():
    with Session() as db:
        yield db
