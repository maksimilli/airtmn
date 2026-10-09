import importlib
import sys
import pytest
from fastapi.testclient import TestClient

PASSWORD = 'test-only-admin-password'

@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setenv('CATALOG_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('CATALOG_SERVER_MODE', '1')
    monkeypatch.setenv('CATALOG_ADMIN_PASSWORD', PASSWORD)
    monkeypatch.setenv('CATALOG_PUBLIC_ORIGIN', 'https://catalog.example')
    monkeypatch.delenv('CATALOG_ADMIN_PASSWORD_FILE', raising=False)
    sys.modules.pop('app.main', None)
    module = importlib.import_module('app.main')
    with TestClient(module.app, base_url='https://catalog.example') as client:
        yield client, module


def sign_in(client, username='admin', password=PASSWORD):
    result = client.post('/api/auth/login', json={'username': username, 'password': password})
    assert result.status_code == 200
    session = client.get('/api/auth/session').json()
    return {'X-CSRF-Token': session['csrf_token'], 'Origin': 'https://catalog.example'}


def test_visitors_read_but_cannot_write_or_list_users(server):
    client, _ = server
    assert client.get('/api/categories').status_code == 200
    assert client.get('/').status_code == 200
    access = client.get('/api/auth/session')
    assert access.json()['can_edit'] is False and access.headers['cache-control'] == 'no-store'
    for method, url, body in [('POST', '/api/components', {'name': 'x'}),
                             ('PUT', '/api/components/1', {'name': 'x'}), ('DELETE', '/api/components/1', None),
                             ('POST', '/api/users', {'username': 'evil', 'password': PASSWORD})]:
        assert client.request(method, url, json=body).status_code == 401
    assert client.post('/api/import', files={'file': ('test.pdf', b'%PDF')}).status_code == 401
    assert client.get('/api/users').status_code == 403
    assert client.get('/api/stats').json()['documents'] == 0


def test_admin_write_requires_session_csrf_and_origin_and_logout_revokes(server):
    client, module = server
    response = client.post('/api/auth/login', json={'username': 'ADMIN', 'password': PASSWORD})
    cookie = response.headers['set-cookie'].lower()
    assert 'httponly' in cookie and 'secure' in cookie and 'samesite=strict' in cookie
    session = client.get('/api/auth/session').json()
    assert session['can_edit'] and session['can_delete'] and session['can_manage_users']
    headers = {'X-CSRF-Token': session['csrf_token']}
    assert client.post('/api/components', json={'name': 'x'}).status_code == 403
    assert client.post('/api/components', headers=headers | {'Origin': 'https://evil.example'}, json={'name': 'x'}).status_code == 403
    identity = client.post('/api/components', headers=headers, json={'name': 'x'}).json()['id']
    assert client.put(f'/api/components/{identity}', headers=headers, json={'name': 'updated'}).status_code == 200
    assert client.delete(f'/api/components/{identity}', headers=headers).status_code == 204
    with module.db() as c:
        hashed = c.execute('SELECT password_hash FROM users').fetchone()[0]
        token = c.execute('SELECT token_hash FROM sessions').fetchone()[0]
        assert PASSWORD not in hashed and hashed.startswith('pbkdf2_sha256$600000$')
        assert client.cookies.get('catalog_session') != token
    assert client.post('/api/auth/logout', headers=headers).status_code == 200
    assert not client.get('/api/auth/session').json()['can_edit']
    with module.db() as c:
        assert c.execute('SELECT COUNT(*) FROM sessions').fetchone()[0] == 0


def test_admin_issues_revokes_rights_and_resets_password_without_lockout(server):
    client, module = server
    headers = sign_in(client)
    payload = {'username': 'second', 'password': 'test-only-second-password', 'role': 'admin'}
    result = client.post('/api/users', headers=headers, json=payload)
    assert result.status_code == 201
    identity = result.json()['id']
    assert client.post('/api/users', headers=headers, json=payload).status_code == 409
    assert all('password_hash' not in user for user in client.get('/api/users').json())
    second = TestClient(module.app, base_url='https://catalog.example')
    second_headers = sign_in(second, 'second', payload['password'])
    assert second.post('/api/components', headers=second_headers, json={'name': 'SECOND'}).status_code == 201
    assert client.put(f'/api/users/{identity}', headers=headers, json={'role': 'viewer', 'enabled': True}).status_code == 200
    assert second.post('/api/components', headers=second_headers, json={'name': 'DENIED'}).status_code == 401
    viewer_headers = sign_in(second, 'second', payload['password'])
    assert not second.get('/api/auth/session').json()['can_edit']
    assert second.post('/api/components', headers=viewer_headers, json={'name': 'DENIED'}).status_code == 403
    assert second.get('/api/users').status_code == 403
    admin_id = client.get('/api/auth/session').json()['user']['id']
    assert client.put(f'/api/users/{admin_id}', headers=headers, json={'role': 'viewer', 'enabled': True}).status_code == 409
    assert client.put(f'/api/users/{admin_id}', headers=headers, json={'role': 'admin', 'enabled': False}).status_code == 409
    assert client.put(f'/api/users/{identity}', headers=headers, json={'role': 'admin', 'enabled': True, 'password': 'test-only-new-password'}).status_code == 200
    assert second.get('/api/auth/session').json()['user'] is None
    assert second.post('/api/auth/login', json={'username':'second','password':payload['password']}).status_code == 401
    sign_in(second, 'second', 'test-only-new-password')
    assert client.put(f'/api/users/{identity}', headers=headers, json={'role': 'admin', 'enabled': False}).status_code == 200
    assert second.get('/api/auth/session').json()['user'] is None
    assert second.post('/api/auth/login', json={'username':'second','password':'test-only-new-password'}).status_code == 401


def test_wrong_password_throttling_expiration_and_csrf(server):
    client, module = server
    assert client.post('/api/auth/login', headers={'Origin':'https://evil.example'}, json={'username':'admin','password':PASSWORD}).status_code == 403
    headers = sign_in(client)
    with module.db() as c:
        c.execute('UPDATE sessions SET expires_at=0')
    assert client.post('/api/components', headers=headers, json={'name':'NO'}).status_code == 401
    for _ in range(10):
        assert client.post('/api/auth/login',json={'username':'admin','password':'wrong'}).status_code == 401
    assert client.post('/api/auth/login',json={'username':'admin','password':PASSWORD}).status_code == 429


def test_password_file_bootstrap_and_missing_password_fail(tmp_path, monkeypatch):
    monkeypatch.setenv('CATALOG_DATA_DIR',str(tmp_path/'data'))
    monkeypatch.setenv('CATALOG_SERVER_MODE','1')
    monkeypatch.delenv('CATALOG_ADMIN_PASSWORD',raising=False)
    monkeypatch.delenv('CATALOG_ADMIN_PASSWORD_FILE',raising=False)
    sys.modules.pop('app.main',None)
    with pytest.raises(RuntimeError, match='administrator password'):
        importlib.import_module('app.main')
    bootstrap_password=' ' + PASSWORD + ' '
    secret=tmp_path/'password';secret.write_text(bootstrap_password + '\n')
    monkeypatch.setenv('CATALOG_ADMIN_PASSWORD_FILE',str(secret))
    sys.modules.pop('app.main',None)
    module=importlib.import_module('app.main')
    with TestClient(module.app,base_url='https://testserver') as client:
        sign_in(client, password=bootstrap_password)
    # Bootstrap never overwrites users on restart.
    secret.write_text('different-long-password')
    sys.modules.pop('app.main',None)
    module=importlib.import_module('app.main')
    with TestClient(module.app,base_url='https://testserver') as client:
        sign_in(client, password=bootstrap_password)


def test_concurrent_admin_downgrades_keep_one_active_admin(server, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from app.database import Session
    client, module = server
    first_headers = sign_in(client)
    first_id = client.get('/api/auth/session').json()['user']['id']
    second_password = 'test-only-second-password'
    second_id = client.post('/api/users', headers=first_headers, json={
        'username': 'second', 'password': second_password, 'role': 'admin'}).json()['id']
    second = TestClient(module.app, base_url='https://catalog.example')
    second_headers = sign_in(second, 'second', second_password)
    barrier = Barrier(2)
    original = Session.lock_users

    def concurrent_lock(session):
        barrier.wait(timeout=10)
        original(session)

    monkeypatch.setattr(Session, 'lock_users', concurrent_lock)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(person.put, f'/api/users/{identity}', headers=headers,
                                   json={'role': 'viewer', 'enabled': True})
                   for person, identity, headers in [(client, first_id, first_headers), (second, second_id, second_headers)]]
        assert sorted(future.result().status_code for future in futures) == [200, 409]
    with module.db() as connection:
        assert connection.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND enabled=1").fetchone()[0] == 1
