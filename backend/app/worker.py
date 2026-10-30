"""Durable database queue. PostgreSQL row locks permit multiple workers."""
import logging
import threading
import time
import os
import signal
import subprocess
import sys
from pathlib import Path
from datetime import timedelta
from sqlalchemy import select, update
from .db import Session, Job, Version, Project, Attachment, Artifact, Proposal, now
from .context import build_context
from .providers import generate, ProviderError
from .artifacts import plan_artifacts, build_artifact, MIMES, render_diagram
from .storage import storage
from .config import settings
from . import agents
from .job_control import JobCancelled, ensure_running, TERMINAL
from .execution import observe_job, emit, add_event, record_stage

log = logging.getLogger(__name__)
ACTIVE = ['Building Context', 'Generating Solution', 'Creating Files', *agents.STAGES]


def stage(db, job, status):
    ensure_running(db, job, lock=True)
    record_stage(db, job, status)
    job.status = status
    job.updated_at = now()
    db.commit()


def validate_diagrams(db, job, context, solution):
    """Validate/repair diagrams once before publishing narrative. Renderer outages leave
    exports independently failed rather than discarding a successful solution."""
    for index, diagram in enumerate(solution.diagrams):
        ensure_running(db, job)
        job.updated_at = now()
        db.commit()
        emit('diagram_validation_started', 'Validating architecture diagram.', {'diagram_index':index+1})
        try:
            render_diagram(diagram.source)
            emit('diagram_validated', 'Architecture diagram validated.', {'diagram_index':index+1})
        except JobCancelled:
            raise
        except Exception:
            if settings.llm_provider != 'demo':
                try:
                    emit('diagram_repair', 'Requesting a bounded Mermaid repair.', {'diagram_index':index+1})
                    fixed = generate(context, {'instruction': 'A diagram failed validation. Repair Mermaid syntax using safe plain-text flowchart or sequenceDiagram syntax.', 'source': diagram.source})
                    candidate = next((d for d in fixed.diagrams if d.kind == diagram.kind), None)
                    if candidate:
                        render_diagram(candidate.source)
                        diagram.source = candidate.source
                except JobCancelled:
                    raise
                except Exception:
                    pass


def create_files(db, job, project, version, documents=None):
    stage(db, job, 'Creating Files')
    artifacts = db.query(Artifact).filter_by(version_id=version.id).all()
    if not artifacts:
        artifacts = plan_artifacts(db, version, documents, job=job)
    selected = [a for a in artifacts if a.id == job.artifact_id] if job.artifact_id else [a for a in artifacts if a.status != 'Completed']
    # Render diagrams before document embeds; package ZIP last.
    selected.sort(key=lambda a: (2 if a.kind == 'zip' else 0 if a.kind.startswith('diagram:') else 1, a.kind))
    cache = {}
    for artifact in selected:
        ensure_running(db, job, lock=True)
        artifact.status = 'Creating Files'
        artifact.error = None
        job.updated_at = now()
        add_event(db, job, 'file_started', 'Creating '+artifact.filename+'.', {'filename':artifact.filename,'format':artifact.kind})
        db.commit()
        try:
            data = build_artifact(db, artifact, version, cache)
            ensure_running(db, job)
            ext = artifact.filename.rsplit('.', 1)[-1]
            key = f'{project.id}/{version.id}/{artifact.id}/{artifact.filename}'
            storage.put(key, data, MIMES.get(ext, 'application/octet-stream'))
            ensure_running(db, job, lock=True)
            artifact.key = key
            artifact.status = 'Completed'
            add_event(db, job, 'file_completed', artifact.filename+' completed.', {'filename':artifact.filename,'format':artifact.kind,'bytes':len(data)})
        except JobCancelled:
            raise
        except Exception:
            ensure_running(db, job, lock=True)
            log.warning('artifact_generation_failed artifact_id=%s kind=%s', artifact.id, artifact.kind)
            artifact.status = 'Failed'
            artifact.error = 'Could not create this file. Check the renderer/storage service and supported diagram syntax, then retry this artifact.'
            add_event(db, job, 'file_failed', artifact.filename+' could not be created.', {'filename':artifact.filename,'format':artifact.kind})
        db.commit()
    # A retried artifact changes the package snapshot: rebuild existing ZIP.
    if job.artifact_id and any(a.id == job.artifact_id and a.kind != 'zip' and a.status == 'Completed' for a in artifacts):
        for package in artifacts:
            if package.kind == 'zip':
                ensure_running(db, job)
                try:
                    data = build_artifact(db, package, version, cache)
                    ensure_running(db, job)
                    key = package.key or f'{project.id}/{version.id}/{package.id}/{package.filename}'
                    storage.put(key, data, MIMES['zip'])
                    ensure_running(db, job, lock=True)
                    package.key, package.status, package.error = key, 'Completed', None
                except JobCancelled:
                    raise
                except Exception:
                    ensure_running(db, job, lock=True)
                    package.status, package.error = 'Failed', 'Package refresh failed. Retry the ZIP artifact.'
                db.commit()
    failures = db.query(Artifact).filter_by(version_id=version.id, status='Failed').count()
    job.error = f'{failures} file(s) failed. Successful results are preserved; retry individual files.' if failures else None
    return failures


def process(job_id):
    with observe_job(job_id, Session):
        emit('worker_started', 'Job worker started.', {'worker_pid':os.getpid()})
        _process(job_id)


def _process(job_id):
    with Session() as db:
        job = db.get(Job, job_id)
        if not job or job.status in TERMINAL:
            return
        project = db.get(Project, job.project_id)
        if job.kind == 'proposal':
            try:
                agents.run(db, job, project, stage=stage, validate_diagrams=validate_diagrams, create_files=create_files)
            except JobCancelled:
                db.rollback()
            except Exception as exc:
                db.rollback()
                job = db.get(Job, job_id)
                if not job or job.status == 'Cancelled':
                    return
                job.error = str(exc) if isinstance(exc, (ProviderError, ValueError)) else 'Proposal workflow failed. Check database, storage and provider configuration, then retry.'
                proposal = db.get(Proposal, job.proposal_id)
                if proposal:
                    proposal.status, proposal.error, proposal.updated_at = 'Failed', job.error, now()
                    agents.AgentBus(db, proposal).send('ProposalCreator', None, 'error', job.error)
                stage(db, job, 'Failed')
            return
        version = db.get(Version, job.version_id)
        try:
            if job.kind == 'solution' and not version.response:
                stage(db, job, 'Building Context')
                attachments = db.query(Attachment).filter_by(project_id=project.id).all()
                history = db.query(Version).filter(Version.project_id == project.id, Version.number < version.number, Version.response.is_not(None)).order_by(Version.number).all()
                context = build_context(version.prompt, version.preferences, attachments, history, project.decisions)
                emit('context_built', 'Reference context assembled.', {'selected_passages':len(context['reference_passages']),'available_passages':sum(len(a.passages) for a in attachments),'history_versions':len(context['history'])})
                version.context_sources = [{'id':r['id'], 'filename':r['filename'], 'reference':r['reference']} for r in context['reference_passages']]
                stage(db, job, 'Generating Solution')
                solution = generate(context)
                ensure_running(db, job)
                validate_diagrams(db, job, context, solution)
                ensure_running(db, job, lock=True)
                version.response = solution.model_dump()
                db.commit()
            create_files(db, job, project, version)
            stage(db, job, 'Completed')
        except JobCancelled:
            db.rollback()
        except Exception as exc:
            db.rollback()
            job = db.get(Job, job_id)
            if not job or job.status == 'Cancelled':
                return
            job.error = str(exc) if isinstance(exc, (ProviderError, ValueError)) else 'Generation failed. Check database, storage and provider configuration, then regenerate.'
            stage(db, job, 'Failed')


def run_once(isolate=False, stop=None):
    with Session() as db:
        # A stalled worker is not allowed to silently hold work forever. Preserve results,
        # but do not automatically repeat provider calls that may have been charged.
        cutoff = now() - timedelta(minutes=20)
        stale = db.scalars(select(Job).where(Job.status.in_(ACTIVE), Job.updated_at < cutoff)).all()
        for old in stale:
            old.status = 'Failed'
            old.error = 'Worker stopped or exceeded its lease. Saved results are preserved. Retry the failed file or regenerate.'
            old.updated_at = now()
            if old.version_id:
                db.execute(update(Artifact).where(Artifact.version_id == old.version_id, Artifact.status.in_(['Queued','Creating Files'])).values(status='Failed', error='Worker stopped during file generation. Retry this artifact.'))
            if old.proposal_id:
                proposal = db.get(Proposal, old.proposal_id)
                if proposal and proposal.status not in ('Live', 'Approved'):
                    proposal.status, proposal.error, proposal.updated_at = 'Failed', old.error, now()
        db.commit()
        candidate = db.scalar(select(Job).where(Job.status == 'Queued').order_by(Job.created_at).with_for_update(skip_locked=True).limit(1))
        if not candidate:
            return False
        # Conditional update also protects SQLite's single-worker development queue.
        result = db.execute(update(Job).where(Job.id == candidate.id, Job.status == 'Queued').values(status='Building Context', attempts=Job.attempts + 1, updated_at=now()))
        if result.rowcount:
            record_stage(db, candidate, 'Building Context')
        db.commit()
        job_id = candidate.id
        if not result.rowcount:
            return False
    if isolate:
        run_isolated(job_id, stop)
    else:
        process(job_id)
    return True


def stop_process(process):
    if process.poll() is not None:
        return
    if os.name == 'nt':
        # Windows virtualenv launchers can create a second Python process.
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=subprocess.CREATE_NO_WINDOW, timeout=5, check=False)
    else:
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        if os.name != 'nt':
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.wait(timeout=3)


def run_isolated(job_id, stop=None):
    with Session() as db:
        job = db.get(Job, job_id)
        if not job or job.status in TERMINAL:
            return
    environment = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1]) + os.pathsep + os.environ.get('PYTHONPATH', '')}
    options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {'start_new_session': True}
    try:
        task = subprocess.Popen([sys.executable, '-m', 'app.worker_task', job_id], env=environment, **options)
    except OSError:
        mark_interrupted(job_id)
        return
    try:
        while task.poll() is None:
            with Session() as db:
                status = db.scalar(select(Job.status).where(Job.id == job_id))
            if status is None or status == 'Cancelled' or stop is not None and stop.is_set():
                stop_process(task)
                break
            if stop is not None:
                stop.wait(.2)
            else:
                time.sleep(.2)
    finally:
        stop_process(task)
    mark_interrupted(job_id)


def mark_interrupted(job_id):
    with Session() as db:
        job = db.get(Job, job_id)
        if job and job.status not in TERMINAL:
            try:
                ensure_running(db, job, lock=True)
            except JobCancelled:
                return
            job.error = 'Worker stopped before completion. Saved results are preserved; retry the request.'
            if job.proposal_id:
                proposal = db.get(Proposal, job.proposal_id)
                if proposal:
                    proposal.status, proposal.error = 'Failed', job.error
            stage(db, job, 'Failed')


def run_forever(stop=None):
    while not stop or not stop.is_set():
        try:
            worked = run_once(isolate=True, stop=stop)
        except Exception:
            log.exception('worker_iteration_failed')
            worked = False
        if not worked:
            if stop:
                stop.wait(1)
            else:
                time.sleep(1)


if __name__ == '__main__':
    settings.validate_runtime()
    run_forever()
