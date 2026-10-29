"""Durable database queue. PostgreSQL row locks permit multiple workers."""
import logging
import threading
import time
from datetime import timedelta
from sqlalchemy import select, update
from .db import Session, Job, Version, Project, Attachment, Artifact, now
from .context import build_context
from .providers import generate, ProviderError
from .artifacts import plan_artifacts, build_artifact, MIMES, render_diagram
from .storage import storage
from .config import settings

log = logging.getLogger(__name__)
ACTIVE = ['Building Context', 'Generating Solution', 'Creating Files']


def stage(db, job, status):
    job.status = status
    job.updated_at = now()
    db.commit()


def process(job_id):
    with Session() as db:
        job = db.get(Job, job_id)
        version = db.get(Version, job.version_id)
        project = db.get(Project, job.project_id)
        try:
            if job.kind == 'solution' and not version.response:
                stage(db, job, 'Building Context')
                attachments = db.query(Attachment).filter_by(project_id=project.id).all()
                history = db.query(Version).filter(Version.project_id == project.id, Version.number < version.number, Version.response.is_not(None)).order_by(Version.number).all()
                context = build_context(version.prompt, version.preferences, attachments, history, project.decisions)
                version.context_sources = [{'id':r['id'], 'filename':r['filename'], 'reference':r['reference']} for r in context['reference_passages']]
                stage(db, job, 'Generating Solution')
                solution = generate(context)
                # Validate/repair diagrams once before publishing narrative. Renderer outages leave
                # exports independently failed rather than discarding a successful solution.
                for diagram in solution.diagrams:
                    job.updated_at = now()
                    db.commit()
                    try:
                        render_diagram(diagram.source)
                    except Exception:
                        if settings.llm_provider != 'demo':
                            try:
                                fixed = generate(context, {'instruction': 'A diagram failed validation. Repair Mermaid syntax using safe plain-text flowchart or sequenceDiagram syntax.', 'source': diagram.source})
                                candidate = next((d for d in fixed.diagrams if d.kind == diagram.kind), None)
                                if candidate:
                                    render_diagram(candidate.source)
                                    diagram.source = candidate.source
                            except Exception:
                                pass
                version.response = solution.model_dump()
                db.commit()
            stage(db, job, 'Creating Files')
            artifacts = db.query(Artifact).filter_by(version_id=version.id).all()
            if not artifacts:
                artifacts = plan_artifacts(db, version)
            selected = [a for a in artifacts if a.id == job.artifact_id] if job.artifact_id else [a for a in artifacts if a.status != 'Completed']
            # Render diagrams before document embeds; package ZIP last.
            selected.sort(key=lambda a: (2 if a.kind == 'zip' else 0 if a.kind.startswith('diagram:') else 1, a.kind))
            cache = {}
            for artifact in selected:
                artifact.status = 'Creating Files'
                artifact.error = None
                job.updated_at = now()
                db.commit()
                try:
                    data = build_artifact(db, artifact, version, cache)
                    ext = artifact.filename.rsplit('.', 1)[-1]
                    key = f'{project.id}/{version.id}/{artifact.id}/{artifact.filename}'
                    storage.put(key, data, MIMES.get(ext, 'application/octet-stream'))
                    artifact.key = key
                    artifact.status = 'Completed'
                except Exception:
                    log.warning('artifact_generation_failed artifact_id=%s kind=%s', artifact.id, artifact.kind)
                    artifact.status = 'Failed'
                    artifact.error = 'Could not create this file. Check the renderer/storage service and supported diagram syntax, then retry this artifact.'
                db.commit()
            # A retried artifact changes the package snapshot: rebuild existing ZIP.
            if job.artifact_id and any(a.id == job.artifact_id and a.kind != 'zip' and a.status == 'Completed' for a in artifacts):
                for package in artifacts:
                    if package.kind == 'zip':
                        try:
                            data = build_artifact(db, package, version, cache)
                            key = package.key or f'{project.id}/{version.id}/{package.id}/{package.filename}'
                            storage.put(key, data, MIMES['zip'])
                            package.key, package.status, package.error = key, 'Completed', None
                        except Exception:
                            package.status, package.error = 'Failed', 'Package refresh failed. Retry the ZIP artifact.'
                        db.commit()
            failures = db.query(Artifact).filter_by(version_id=version.id, status='Failed').count()
            job.error = f'{failures} file(s) failed. Successful results are preserved; retry individual files.' if failures else None
            stage(db, job, 'Completed')
        except Exception as exc:
            db.rollback()
            job = db.get(Job, job_id)
            job.error = str(exc) if isinstance(exc, (ProviderError, ValueError)) else 'Generation failed. Check database, storage and provider configuration, then regenerate.'
            stage(db, job, 'Failed')


def run_once():
    with Session() as db:
        # A stalled worker is not allowed to silently hold work forever. Preserve results,
        # but do not automatically repeat provider calls that may have been charged.
        cutoff = now() - timedelta(minutes=20)
        stale = db.scalars(select(Job).where(Job.status.in_(ACTIVE), Job.updated_at < cutoff)).all()
        for old in stale:
            old.status = 'Failed'
            old.error = 'Worker stopped or exceeded its lease. Saved results are preserved. Retry the failed file or regenerate.'
            old.updated_at = now()
            db.execute(update(Artifact).where(Artifact.version_id == old.version_id, Artifact.status.in_(['Queued','Creating Files'])).values(status='Failed', error='Worker stopped during file generation. Retry this artifact.'))
        db.commit()
        candidate = db.scalar(select(Job).where(Job.status == 'Queued').order_by(Job.created_at).with_for_update(skip_locked=True).limit(1))
        if not candidate:
            return False
        # Conditional update also protects SQLite's single-worker development queue.
        result = db.execute(update(Job).where(Job.id == candidate.id, Job.status == 'Queued').values(status='Building Context', attempts=Job.attempts + 1, updated_at=now()))
        db.commit()
        job_id = candidate.id
        if not result.rowcount:
            return False
    process(job_id)
    return True


def run_forever(stop=None):
    while not stop or not stop.is_set():
        try:
            worked = run_once()
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
