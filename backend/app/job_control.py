"""Persisted cancellation shared by the API and generation workers."""
from sqlalchemy import select
from .db import Job

TERMINAL = ['Completed', 'Failed', 'Cancelled']


class JobCancelled(Exception):
    pass


def ensure_running(db, job, lock=False):
    with db.no_autoflush:
        query = select(Job.status).where(Job.id == job.id)
        if lock:
            query = query.with_for_update()
        status = db.scalar(query)
    if status is None or status == 'Cancelled':
        db.rollback()
        raise JobCancelled()
