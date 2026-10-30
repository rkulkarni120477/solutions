"""Convert existing library files into content-free formats in place."""
from app.db import Session, ProposalTemplate, Job
from app.templates import prepare_template
from app.storage import storage
from app.job_control import TERMINAL


def main():
    count = 0
    with Session() as db:
        if db.query(Job).filter(Job.status.notin_(TERMINAL)).first():
            raise RuntimeError('Wait for active generation jobs to finish before cleaning the template library.')
        for row in db.query(ProposalTemplate).all():
            kind, data = prepare_template(row.filename, storage.get(row.key))
            storage.put(row.key, data)
            row.filename = row.filename.rsplit('.', 1)[0] + '.' + kind
            row.size = len(data)
            db.commit()
            count += 1
    print(f'Converted {count} library entries to content-free formats. Generated proposals were not modified.')


if __name__ == '__main__':
    main()
