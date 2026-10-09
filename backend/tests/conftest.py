"""Optionally run existing API/auth tests against an isolated PostgreSQL schema."""
import os
import uuid

import pytest
from sqlalchemy import text
from app.database import Database


@pytest.fixture(autouse=True)
def database_backend(tmp_path, monkeypatch):
    url = os.getenv('CATALOG_TEST_POSTGRES_URL')
    if not url:
        monkeypatch.delenv('DATABASE_URL', raising=False)
        monkeypatch.delenv('CATALOG_DATABASE_PASSWORD_FILE', raising=False)
        yield
        return
    control = Database(tmp_path, url)
    assert control.postgres, 'Use a dedicated PostgreSQL test database'
    schema = 'airtmn_test_' + uuid.uuid4().hex
    with control.engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA {schema}'))
    test_url = control.engine.url.update_query_dict({'options': '-csearch_path=' + schema})
    monkeypatch.setenv('DATABASE_URL', test_url.render_as_string(hide_password=False))
    monkeypatch.delenv('CATALOG_DATABASE_PASSWORD_FILE', raising=False)
    original = Database.__init__
    instances = []

    def register(instance, *args, **kwargs):
        original(instance, *args, **kwargs)
        instances.append(instance)

    monkeypatch.setattr(Database, '__init__', register)
    try:
        yield
    finally:
        for instance in instances:
            instance.engine.dispose()
        with control.engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        control.engine.dispose()
