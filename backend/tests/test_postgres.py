import hashlib
import importlib
import os
import sqlite3
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path

import fitz
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import Database
from app.transfer import copy_sqlite
from test_api import client

pytestmark = pytest.mark.skipif(not os.getenv('CATALOG_TEST_POSTGRES_URL'),
                                reason='Requires isolated PostgreSQL test database')


def source_catalog(path, missing_pdf=False):
    path.mkdir()
    with fitz.open() as pdf:
        pdf.new_page().insert_text((40, 40), 'VRRM = 100 V\nIF(AV) = 500 mA')
        content = pdf.tobytes()
    identity = hashlib.sha256(content).hexdigest()
    with sqlite3.connect(path / 'catalog.sqlite3') as connection:
        connection.executescript('''
            CREATE TABLE documents(id TEXT PRIMARY KEY, filename TEXT NOT NULL);
            CREATE TABLE components(id INTEGER PRIMARY KEY,name TEXT NOT NULL,manufacturer TEXT NOT NULL,
                package TEXT NOT NULL,description TEXT NOT NULL,document_id TEXT REFERENCES documents(id),UNIQUE(name,manufacturer));
            CREATE TABLE parameters(id INTEGER PRIMARY KEY,component_id INTEGER REFERENCES components(id),
                code TEXT NOT NULL,value REAL NOT NULL,unit TEXT NOT NULL,kind TEXT NOT NULL,
                conditions TEXT NOT NULL,page INTEGER,evidence TEXT NOT NULL);
            CREATE TABLE users(id INTEGER PRIMARY KEY,username TEXT NOT NULL UNIQUE,password_hash TEXT NOT NULL,
                role TEXT NOT NULL,enabled INTEGER NOT NULL);
            CREATE TABLE sessions(token_hash TEXT PRIMARY KEY,user_id INTEGER,csrf_token TEXT,expires_at INTEGER);
        ''')
        connection.execute('INSERT INTO documents VALUES(?,?)', (identity, 'original.pdf'))
        connection.execute('INSERT INTO components VALUES(42,?,?,?,?,?)', ('LEGACY', 'Example', 'DO-41', 'Saved', identity))
        connection.execute('INSERT INTO parameters VALUES(12,42,?,?,?,?,?,?,?)', ('IF_AV', .5, 'A', 'max', 'TA = 75 C', 1, 'Evidence'))
        connection.execute("INSERT INTO users VALUES(7,'existing','preserved-password-hash','admin',1)")
        connection.execute("INSERT INTO sessions VALUES('old',7,'csrf',999999999)")
        if missing_pdf:
            connection.execute('INSERT INTO documents VALUES(?,?)', ('f' * 64, 'missing.pdf'))
    (path / (identity + '.pdf')).write_bytes(content)
    return identity, content


def target_database(tmp_path):
    return Database(tmp_path, os.environ['DATABASE_URL'])


def test_pdf_persists_without_local_files_and_after_restart(client, tmp_path, monkeypatch):
    with fitz.open() as pdf:
        pdf.new_page().insert_text((40, 40), 'VRRM = 100 V\nIF(AV) = 500 mA')
        content = pdf.tobytes()
    result = client.post('/api/import', files={'file': ('original.pdf', content)}).json()
    identity = result['document_id']
    assert result['parameters'] and not list(tmp_path.glob('*.pdf'))
    assert client.get('/api/documents').json()[0]['id'] == identity
    assert 'content' not in client.get('/api/documents').json()[0]
    assert client.get(f'/api/documents/{identity}/pages/1').headers['content-type'] == 'image/png'
    assert client.get(f'/api/documents/{identity}/pages/2').status_code == 404
    sys.modules['app.main'].db.engine.dispose()
    monkeypatch.setenv('CATALOG_DATA_DIR', str(tmp_path / 'new-empty-container'))
    sys.modules.pop('app.main', None)
    module = importlib.import_module('app.main')
    with TestClient(module.app) as restarted:
        assert restarted.get('/api/health').json()['database'] == 'postgresql'
        assert restarted.get('/api/documents/' + identity).content == content
        assert restarted.post('/api/import', files={'file': ('renamed.pdf', content)}).json()['duplicate']
        assert len(restarted.get('/api/documents').json()) == 1


def test_case_insensitive_search_and_conflict_do_not_break_next_transaction(client):
    payload = {'name': 'ДИОД-TEST', 'manufacturer': 'Example', 'parameters': []}
    assert client.post('/api/components', json=payload).status_code == 201
    assert len(client.get('/api/components', params={'q': 'диод-test', 'manufacturer': 'EXAMPLE'}).json()) == 1
    assert client.post('/api/components', json=payload).status_code == 409
    assert client.post('/api/components', json=payload | {'name': 'NEXT'}).status_code == 201
    assert client.get('/api/stats').json()['components'] == 2


def test_transfer_preserves_ids_hashes_pdf_and_source_and_resets_sequences(tmp_path):
    source = tmp_path / 'source'
    identity, content = source_catalog(source)
    original = (source / 'catalog.sqlite3').read_bytes()
    target = target_database(tmp_path)
    counts = copy_sqlite(source, target)
    assert counts == {'documents': 1, 'components': 1, 'parameters': 1, 'users': 1}
    assert target.document_content(identity) == content
    assert (source / 'catalog.sqlite3').read_bytes() == original
    with target() as connection:
        assert connection.execute('SELECT source FROM parameters').fetchone()[0] == 'text'
        assert connection.execute('SELECT COUNT(*) FROM sessions').fetchone()[0] == 0
        assert connection.execute('SELECT password_hash FROM users WHERE id=7').fetchone()[0] == 'preserved-password-hash'
        created = connection.execute("INSERT INTO components(name,manufacturer,package,description) VALUES('NEXT','','','') RETURNING id").fetchone()[0]
        assert created > 42
        user = connection.execute("INSERT INTO users(username,password_hash,role) VALUES('new','hash','viewer') RETURNING id").fetchone()[0]
        assert user > 7
    with pytest.raises(ValueError, match='must be empty'):
        copy_sqlite(source, target)
    assert target.document_content(identity) == content


@pytest.mark.parametrize('damaged', ['missing', 'checksum'])
def test_failed_transfer_rolls_back_all_records(tmp_path, damaged):
    source = tmp_path / 'source'
    identity, _ = source_catalog(source, missing_pdf=damaged == 'missing')
    if damaged == 'checksum':
        (source / (identity + '.pdf')).write_bytes(b'damaged')
    target = target_database(tmp_path)
    with pytest.raises(ValueError, match='missing|checksum'):
        copy_sqlite(source, target)
    with target() as connection:
        for table in ['documents', 'components', 'parameters', 'users']:
            assert connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0


@contextmanager
def another_schema(path):
    control = target_database(path)
    schema = 'airtmn_restore_' + uuid.uuid4().hex
    with control.engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA {schema}'))
    url = control.engine.url.update_query_dict({'options': '-csearch_path=' + schema})
    database = Database(path, url.render_as_string(hide_password=False))
    try:
        yield database
    finally:
        database.engine.dispose()
        with control.engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        control.engine.dispose()


def test_postgres_backup_restore_includes_pdf_accounts_and_clears_sessions(tmp_path):
    import importlib.util
    location = Path(__file__).resolve().parents[2] / 'deploy' / 'backup.py'
    spec = importlib.util.spec_from_file_location('postgres_backup', location)
    backup = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(backup)
    source = tmp_path / 'source'
    identity, content = source_catalog(source)
    database = target_database(tmp_path)
    copy_sqlite(source, database)
    with database() as connection:
        connection.execute("INSERT INTO sessions VALUES('old',7,'csrf',999999999)")
    archive = tmp_path / 'backup.tar.gz'
    assert backup.create(tmp_path, archive, os.environ['DATABASE_URL']) == 2
    with another_schema(tmp_path) as restored:
        url = restored.engine.url.render_as_string(hide_password=False)
        assert backup.restore(tmp_path, archive, url) == 2
        assert restored.document_content(identity) == content
        with restored() as connection:
            assert connection.execute('SELECT name FROM components WHERE id=42').fetchone()[0] == 'LEGACY'
            assert connection.execute('SELECT COUNT(*) FROM sessions').fetchone()[0] == 0
            assert connection.execute('SELECT password_hash FROM users WHERE id=7').fetchone()[0] == 'preserved-password-hash'
        with pytest.raises(ValueError, match='must be empty'):
            backup.restore(tmp_path, archive, url)
