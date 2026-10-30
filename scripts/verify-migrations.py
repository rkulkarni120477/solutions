"""Verify migration upgrade/downgrade/re-upgrade against an isolated SQLite database."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from sqlalchemy import create_engine, inspect

with tempfile.TemporaryDirectory(prefix='workspace-migrations-') as temp:
    url='sqlite:///'+str(Path(temp)/'migrations.db').replace('\\','/')
    env={**os.environ,'DATABASE_URL':url}
    for action in [('upgrade','head'),('downgrade','base'),('upgrade','head')]:
        subprocess.run([sys.executable,'-m','alembic','-c','backend/alembic.ini',*action],env=env,check=True)
        engine=create_engine(url)
        tables=set(inspect(engine).get_table_names())
        expected={'users','projects','versions','attachments','jobs','artifacts','audit_events','proposals','agent_messages','response_documents','proposal_templates','job_events'}
        assert (expected <= tables) if action[0]=='upgrade' else not (expected & tables)
        engine.dispose()
    # Detect drift between the frozen migration and current SQLAlchemy models.
    subprocess.run([sys.executable,'-m','alembic','-c','backend/alembic.ini','check'],env=env,check=True)
print('PASS: migration round-trip and model parity')
