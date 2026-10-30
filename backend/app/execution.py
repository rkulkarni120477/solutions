"""Observed backend execution metadata. Never record prompts or response bodies."""
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import timezone
from sqlalchemy import select
from .db import Job, JobEvent, now
from .job_control import TERMINAL

log = logging.getLogger(__name__)
_observer = ContextVar('job_execution_observer', default=None)


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def actor(kind, stage):
    if stage == 'Queued':
        return ('RequestQueue', 'app.worker.run_once', 'Worker')
    if stage in TERMINAL:
        return ('JobWorker', 'app.worker.process', 'Worker')
    if kind == 'proposal':
        mapping = {
            'Building Context': ('OrchestratorAgent', 'app.agents.OrchestratorAgent.execute', 'Agent'),
            'Collecting Requirements': ('RequirementsCollectorAgent', 'app.agents.RequirementsCollectorAgent.run', 'Agent'),
            'Planning Proposal': ('ProposalCreatorAgent', 'app.agents.ProposalCreatorAgent.plan', 'Agent'),
            'Generating Solution': ('ProposalCreatorAgent', 'app.agents.ProposalCreatorAgent.run', 'Agent'),
            'Estimating': ('EstimationsAgent', 'app.agents.EstimationsAgent.run', 'Agent'),
            'Planning Resources': ('ResourcesAgent', 'app.agents.ResourcesAgent.run', 'Agent'),
            'Defining Methodology': ('DeliveryMethodologyAgent', 'app.agents.DeliveryMethodologyAgent.run', 'Agent'),
            'Preparing Documents': ('ProposalCreatorAgent', 'app.agents.ProposalCreatorAgent.run', 'Agent'),
            'Creating Files': ('DocumentsAgent', 'app.worker.create_files', 'Agent'),
        }
    else:
        mapping = {
            'Building Context': ('ContextBuilder', 'app.context.build_context', 'Worker step'),
            'Generating Solution': ('SolutionArchitect', 'app.providers.generate', 'LLM step'),
            'Creating Files': ('DocumentBuilder', 'app.worker.create_files', 'Worker step'),
        }
    return mapping.get(stage, ('JobWorker', 'app.worker.process', 'Worker'))


def add_event(db, job, kind, message, details=None, stage=None):
    stage = stage or job.status
    agent, implementation, agent_type = actor(job.kind, stage)
    event = JobEvent(job_id=job.id, agent=agent, implementation=implementation, agent_type=agent_type,
                     stage=stage, kind=kind, message=message, details=details or {})
    db.add(event)
    return event


def record_stage(db, job, status):
    with db.no_autoflush:
        previous = db.scalar(select(JobEvent).where(JobEvent.job_id == job.id, JobEvent.kind == 'stage_started').order_by(JobEvent.created_at.desc()).limit(1))
    if previous and previous.stage == status:
        return
    if previous:
        with db.no_autoflush:
            finished = db.scalar(select(JobEvent.id).where(JobEvent.job_id == job.id, JobEvent.kind == 'stage_finished', JobEvent.details['start_event_id'].as_string() == previous.id).limit(1))
        if not finished:
            elapsed = max(0, int((now() - utc(previous.created_at)).total_seconds()*1000))
            add_event(db, job, 'stage_finished', f'{previous.stage} finished.', {'start_event_id':previous.id,'duration_ms':elapsed,'outcome':status if status in TERMINAL else 'Completed'}, previous.stage)
    if status in TERMINAL:
        add_event(db, job, 'workflow_'+status.lower(), 'Workflow '+status.lower()+'.', stage=status)
    else:
        add_event(db, job, 'stage_started', status+' started.', stage=status)


def emit(kind, message, details=None):
    observer = _observer.get()
    if observer is not None:
        observer(kind, message, details or {})


@contextmanager
def observe_job(job_id, sessions):
    def record(kind, message, details):
        try:
            with sessions() as db:
                job = db.get(Job, job_id)
                if not job or job.status == 'Cancelled':
                    return
                add_event(db, job, kind, message, details)
                db.commit()
        except Exception:
            # Observability must not fail generation or log sensitive exception data.
            log.warning('execution_event_unavailable job_id=%s event=%s', job_id, kind)
    token = _observer.set(record)
    try:
        yield
    finally:
        _observer.reset(token)


def execution_view(db, job):
    # Read at most 300 recent operational events; never reconstruct historical logs.
    events = list(reversed(db.scalars(select(JobEvent).where(JobEvent.job_id == job.id).order_by(JobEvent.created_at.desc()).limit(300)).all()))
    finishes = {e.details.get('start_event_id'):e for e in events if e.kind == 'stage_finished'}
    stages = []
    for event in events:
        if event.kind != 'stage_started':
            continue
        finish = finishes.get(event.id)
        stages.append({'stage':event.stage,'agent':event.agent,'implementation':event.implementation,'agent_type':event.agent_type,
                       'started_at':utc(event.created_at),'finished_at':utc(finish.created_at) if finish else None,
                       'duration_ms':finish.details.get('duration_ms') if finish else None,
                       'outcome':finish.details.get('outcome') if finish else 'Running' if job.status not in TERMINAL else job.status})
    provider = next((e.details for e in reversed(events) if e.kind == 'provider_request_started'), None)
    agent, implementation, agent_type = actor(job.kind, job.status)
    return {'job_id':job.id,'status':job.status,'attempts':job.attempts,'created_at':utc(job.created_at),'updated_at':utc(job.updated_at),'server_time':now(),
            'current':{'agent':agent,'implementation':implementation,'agent_type':agent_type,'stage':job.status},
            'handlers':[{'stage':stage,'agent':actor(job.kind,stage)[0],'implementation':actor(job.kind,stage)[1],'agent_type':actor(job.kind,stage)[2]} for stage in ['Queued','Building Context','Collecting Requirements','Planning Proposal','Generating Solution','Estimating','Planning Resources','Defining Methodology','Preparing Documents','Creating Files']],
            'provider':provider,'recorded':bool(events),'stages':stages,
            'activity':[{'id':e.id,'agent':e.agent,'implementation':e.implementation,'agent_type':e.agent_type,'stage':e.stage,'kind':e.kind,'message':e.message,'details':e.details,'created_at':utc(e.created_at)} for e in events]}
