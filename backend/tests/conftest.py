import os
import sys
from pathlib import Path
os.environ['EMBEDDED_WORKER'] = 'false'
os.environ['LLM_PROVIDER'] = 'demo'
os.environ['AUTH_MODE'] = 'demo'
os.environ['STORAGE_BACKEND'] = 'local'
os.environ['ENVIRONMENT'] = 'test'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from app.db import Base, get_db
from app.main import app
from app.storage import storage
from app import worker


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    engine = create_engine(f'sqlite:///{tmp_path / "test.db"}', connect_args={'check_same_thread':False})
    @event.listens_for(engine, 'connect')
    def pragma(conn, _):
        conn.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    def override():
        with sessions() as db:
            yield db
    app.dependency_overrides[get_db] = override
    monkeypatch.setattr(worker, 'Session', sessions)
    monkeypatch.setattr(storage, 'root', tmp_path / 'objects')
    # No app lifespan: use the test database and explicit durable worker steps.
    alice = TestClient(app)
    bob = TestClient(app)
    for client in [alice,bob]:
        client.headers['X-Workspace-Request']='1'
        assert client.post('/api/auth/demo').status_code == 200
    yield alice,bob,sessions
    alice.close()
    bob.close()
    app.dependency_overrides.clear()
    engine.dispose()
