"""Schedule daily: python -m app.retention. Audit records contain metadata only."""
from datetime import timedelta
from sqlalchemy import select, delete
from .config import settings
from .db import Session, Project, Attachment, Artifact, Job, Audit, ResponseDocument, now
from .worker import ACTIVE
from .storage import storage


def cleanup():
    cutoff = now() - timedelta(days=settings.retention_days)
    count = 0
    with Session() as db:
        for project in db.scalars(select(Project).where(Project.updated_at < cutoff)):
            if db.scalar(select(Job.id).where(Job.project_id == project.id, Job.status.in_(['Queued', *ACTIVE])).limit(1)):
                continue
            for a in db.scalars(select(Attachment).where(Attachment.project_id == project.id)):
                storage.delete(a.key)
            for a in db.scalars(select(Artifact).where(Artifact.project_id == project.id)):
                if a.key:
                    storage.delete(a.key)
            for d in db.scalars(select(ResponseDocument).where(ResponseDocument.project_id == project.id)):
                storage.delete(d.key)
            db.add(Audit(user_id=project.owner_id, action='retention_deleted', resource_id=project.id))
            db.delete(project)
            count += 1
        db.execute(delete(Audit).where(Audit.created_at < cutoff))
        db.commit()
    return count


if __name__ == '__main__':
    print(f'Removed {cleanup()} expired projects.')
