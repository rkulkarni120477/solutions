import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings


@pytest.fixture
def local_auth(monkeypatch):
    monkeypatch.setattr(settings, 'auth_mode', 'local')
    monkeypatch.setattr(settings, 'local_admin_username', 'admin')
    monkeypatch.setattr(settings, 'local_admin_password', 'local-test-password')
    monkeypatch.setattr(settings, 'local_auto_login', True)


def test_local_credentials_and_persistent_auto_session(workspace, local_auth):
    alice, bob, _ = workspace
    alice.post('/api/auth/logout')
    assert alice.get('/api/me').status_code == 401
    assert alice.post('/api/auth/local', json={'username': 'admin', 'password': 'incorrect'}).status_code == 401
    assert alice.post('/api/auth/local', json={'username': 'admin', 'password': 'local-test-password'}).json() == {'name': 'admin'}
    pid = alice.post('/api/projects', json={'title': 'Persistent admin project'}).json()['id']
    assert bob.post('/api/auth/auto').json() == {'name': 'admin'}
    assert bob.get('/api/projects/' + pid).status_code == 200
    alice.post('/api/auth/logout')
    assert alice.get('/api/me').status_code == 401
    assert alice.post('/api/auth/auto').status_code == 200
    assert alice.get('/api/projects/' + pid).status_code == 200
    config = alice.get('/api/config').json()
    assert config['auto_login'] is True
    assert 'password' not in str(config) and 'local-test-password' not in str(config)


def test_auto_auth_requires_enabled_local_mode_and_request_protection(workspace, monkeypatch):
    alice, _, _ = workspace
    assert alice.get('/api/config').json()['auto_login'] is False
    assert alice.post('/api/auth/auto').status_code == 404
    monkeypatch.setattr(settings, 'auth_mode', 'local')
    monkeypatch.setattr(settings, 'local_admin_password', 'local-test-password')
    monkeypatch.setattr(settings, 'local_auto_login', False)
    assert alice.post('/api/auth/auto').status_code == 404
    monkeypatch.setattr(settings, 'local_auto_login', True)
    anonymous = TestClient(app)
    assert anonymous.post('/api/auth/auto').status_code == 403
    assert alice.post('/api/auth/auto', headers={'Origin':'https://unrelated.example'}).status_code == 403
    monkeypatch.setattr(settings, 'environment', 'production')
    assert alice.get('/api/config').json()['auto_login'] is False
    assert alice.post('/api/auth/auto').status_code == 404
    anonymous.close()


def test_older_open_pages_sign_in_to_same_admin_account(workspace, local_auth, monkeypatch):
    alice, bob, _ = workspace
    assert alice.post('/api/auth/demo').json() == {'name':'admin'}
    pid = alice.post('/api/projects', json={'title':'Older page compatibility'}).json()['id']
    assert bob.post('/api/auth/auto').status_code == 200
    assert bob.get('/api/projects/' + pid).status_code == 200
    monkeypatch.setattr(settings, 'local_auto_login', False)
    assert alice.post('/api/auth/demo').status_code == 404
    monkeypatch.setattr(settings, 'local_auto_login', True)
    monkeypatch.setattr(settings, 'environment', 'production')
    assert alice.post('/api/auth/demo').status_code == 404


def test_app_html_is_not_cached(workspace):
    alice, _, _ = workspace
    response = alice.get('/')
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
