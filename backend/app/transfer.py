"""Portable catalog transfer. Originals are read-only; targets must be empty."""
import hashlib
import re
import sqlite3
from contextlib import closing
from pathlib import Path

from sqlalchemy import select
from app.database import Database, metadata

TABLES = ('documents', 'components', 'parameters', 'users')


def copy_sqlite(source: Path, target: Database):
    if not target.postgres:
        raise ValueError('A PostgreSQL target is required')
    path = Path(source) / 'catalog.sqlite3'
    if not path.is_file():
        raise ValueError('Source SQLite catalog not found')
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as legacy:
        legacy.row_factory = sqlite3.Row
        legacy.execute('BEGIN')
        if legacy.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Source SQLite integrity check failed')
        if legacy.execute('PRAGMA foreign_key_check').fetchone():
            raise ValueError('Source has broken relationships')
        tables = {row[0] for row in legacy.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'documents', 'components', 'parameters'}.issubset(tables):
            raise ValueError('Source is not a component catalog')
        target.initialize()
        counts = {}
        with target() as session:
            if session.postgres:
                session.execute('LOCK TABLE documents,components,parameters,users,sessions,login_attempts IN EXCLUSIVE MODE')
            else:
                session.execute('BEGIN IMMEDIATE')
            for table in metadata.tables:
                if session.execute(f'SELECT 1 FROM {table} LIMIT 1').fetchone():
                    raise ValueError('Target database must be empty; existing data will not be overwritten')
            for name in TABLES:
                counts[name] = 0
                if name not in tables:
                    continue
                table = metadata.tables[name]
                for ordinal, original in enumerate(legacy.execute(f'SELECT * FROM {name} ORDER BY rowid'), 1):
                    row = dict(original)
                    if name == 'documents':
                        identity = row['id']
                        if not re.fullmatch('[0-9a-f]{64}', identity):
                            raise ValueError('Invalid document identity')
                        content = row.get('content')
                        if content is None:
                            pdf = Path(source) / (identity + '.pdf')
                            if not pdf.is_file():
                                raise ValueError('A referenced PDF is missing')
                            content = pdf.read_bytes()
                        if hashlib.sha256(content).hexdigest() != identity:
                            raise ValueError('PDF checksum does not match the document identity')
                        row.update(size=len(content), content=content,
                                   created_at=row.get('created_at') or ordinal)
                    if name == 'parameters' and 'source' not in row:
                        row['source'] = 'text' if row.get('evidence') else 'manual'
                    row = {key: value for key, value in row.items() if key in table.c}
                    session.connection.execute(table.insert().values(**row))
                    counts[name] += 1
            if target.postgres:
                for name in ('components', 'parameters', 'users'):
                    session.execute(f"SELECT setval(pg_get_serial_sequence('{name}','id'), COALESCE(MAX(id),1), MAX(id) IS NOT NULL) FROM {name}")
        return counts


def snapshot_postgres(source: Database, destination: Path):
    """One repeatable-read snapshot, including PDF bytes and accounts, without sessions."""
    destination.mkdir(parents=True, exist_ok=True)
    target = Database(destination)
    target.initialize()
    try:
        with source.engine.connect().execution_options(isolation_level='REPEATABLE READ') as connection:
            with connection.begin(), target() as output:
                connection.exec_driver_sql('SET TRANSACTION READ ONLY')
                for name in TABLES:
                    table = metadata.tables[name]
                    columns = [column for column in table.c if column.name != 'content']
                    for original in connection.execute(select(*columns)).mappings():
                        row = dict(original)
                        if name == 'documents':
                            content = connection.execute(select(table.c.content).where(table.c.id == row['id'])).scalar_one()
                            if content is None or hashlib.sha256(content).hexdigest() != row['id']:
                                raise ValueError('Missing or damaged PDF in PostgreSQL')
                            (destination / (row['id'] + '.pdf')).write_bytes(content)
                        output.connection.execute(table.insert().values(**row))
    finally:
        target.engine.dispose()
