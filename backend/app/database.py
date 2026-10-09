"""Shared transactional storage: PostgreSQL for hosting, SQLite for local use."""
import re
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import (Column, Float, ForeignKey, Index, Integer, LargeBinary,
                        MetaData, Table, Text, UniqueConstraint,
                        create_engine, event, inspect, text)
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

metadata = MetaData()
documents = Table('documents', metadata,
    Column('id', Text, primary_key=True), Column('filename', Text, nullable=False),
    Column('pages', Integer, nullable=False, server_default='0'),
    Column('size', Integer, nullable=False, server_default='0'),
    Column('content', LargeBinary),
    Column('created_at', Integer, nullable=False, server_default='0'))
components = Table('components', metadata,
    Column('id', Integer, primary_key=True), Column('name', Text, nullable=False),
    Column('manufacturer', Text, nullable=False), Column('package', Text, nullable=False),
    Column('description', Text, nullable=False),
    Column('document_id', Text, ForeignKey('documents.id')),
    Column('category', Text, nullable=False, server_default='diode'),
    UniqueConstraint('name', 'manufacturer'))
parameters = Table('parameters', metadata,
    Column('id', Integer, primary_key=True),
    Column('component_id', Integer, ForeignKey('components.id', ondelete='CASCADE')),
    Column('code', Text, nullable=False), Column('value', Float(precision=53), nullable=False),
    Column('unit', Text, nullable=False), Column('kind', Text, nullable=False),
    Column('conditions', Text, nullable=False), Column('page', Integer),
    Column('evidence', Text, nullable=False),
    Column('source', Text, nullable=False, server_default='manual'),
    Column('confidence', Float(precision=53)))
Index('parameter_search', parameters.c.component_id, parameters.c.code,
      parameters.c.kind, parameters.c.value)
users = Table('users', metadata,
    Column('id', Integer, primary_key=True), Column('username', Text, nullable=False, unique=True),
    Column('password_hash', Text, nullable=False), Column('role', Text, nullable=False),
    Column('enabled', Integer, nullable=False, server_default='1'))
sessions = Table('sessions', metadata,
    Column('token_hash', Text, primary_key=True),
    Column('user_id', Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
    Column('csrf_token', Text, nullable=False), Column('expires_at', Integer, nullable=False))
Table('login_attempts', metadata,
    Column('ip', Text, primary_key=True), Column('attempts', Integer, nullable=False),
    Column('started_at', Integer, nullable=False))


class Row:
    """Keep named and positional access consistent across both database drivers."""
    def __init__(self, value):
        self.value = value

    def keys(self):
        return self.value._mapping.keys()

    def __getitem__(self, key):
        return self.value[key] if isinstance(key, int) else self.value._mapping[key]

    def __iter__(self):
        return iter(self.value)


class Result:
    def __init__(self, value):
        self.value = value
        self.rowcount = value.rowcount

    def fetchone(self):
        row = self.value.fetchone()
        return Row(row) if row is not None else None

    def fetchall(self):
        return [Row(row) for row in self.value.fetchall()]

    def __iter__(self):
        return (Row(row) for row in self.value)


class Session:
    def __init__(self, connection):
        self.connection = connection
        self.postgres = connection.dialect.name == 'postgresql'

    def execute(self, sql, values=()):
        # SQL is application-owned; values are always bound, never interpolated.
        parts = sql.split('?')
        if len(parts) - 1 != len(values):
            raise ValueError('SQL placeholder count does not match bound values')
        statement = ''.join(part + (f':v{i}' if i < len(values) else '')
                            for i, part in enumerate(parts))
        return Result(self.connection.execute(text(statement),
                      {f'v{i}': value for i, value in enumerate(values)}))

    def lock_users(self):
        # Serialise changes so two admins cannot concurrently remove the last admin.
        self.execute('LOCK TABLE users IN EXCLUSIVE MODE' if self.postgres else 'BEGIN IMMEDIATE')


class Database:
    def __init__(self, data: Path, url: str = '', password_file: str = ''):
        self.data = Path(data)
        if not url:
            url = 'sqlite:///' + str(self.data / 'catalog.sqlite3')
        if url.startswith(('postgres://', 'postgresql://')):
            url = re.sub(r'^postgres(?:ql)?://', 'postgresql+psycopg://', url)
        if not url.startswith(('postgresql+psycopg://', 'sqlite:///')):
            raise ValueError('DATABASE_URL must use PostgreSQL or SQLite')
        url = make_url(url)
        if password_file:
            url = url.set(password=Path(password_file).read_text(encoding='utf-8').rstrip('\r\n'))
        options = dict(hide_parameters=True, pool_pre_ping=True)
        if url.drivername == 'sqlite':
            options.update(poolclass=NullPool, connect_args={'check_same_thread': False, 'timeout': 30})
        else:
            options.update(pool_size=5, max_overflow=5, pool_timeout=10, pool_recycle=300,
                           connect_args={'connect_timeout': 10})
        self.engine = create_engine(url, **options)
        self.postgres = self.engine.dialect.name == 'postgresql'
        if not self.postgres:
            @event.listens_for(self.engine, 'connect')
            def configure_sqlite(connection, _):
                connection.execute('PRAGMA foreign_keys=ON')

    @contextmanager
    def __call__(self):
        with self.engine.begin() as connection:
            yield Session(connection)

    def initialize(self):
        with self() as session:
            if self.postgres:
                session.execute('SELECT pg_advisory_xact_lock(684179023)')
            metadata.create_all(session.connection)
            additions = {
                'parameters': {'source': "TEXT NOT NULL DEFAULT 'manual'", 'confidence': 'DOUBLE PRECISION'},
                'components': {'category': "TEXT NOT NULL DEFAULT 'diode'"},
                'documents': {'pages': 'INTEGER NOT NULL DEFAULT 0', 'size': 'INTEGER NOT NULL DEFAULT 0',
                    'content': 'BYTEA' if self.postgres else 'BLOB', 'created_at': 'INTEGER NOT NULL DEFAULT 0'},
            }
            for table, columns in additions.items():
                existing = {column['name'] for column in inspect(session.connection).get_columns(table)}
                for column, definition in columns.items():
                    if column not in existing:
                        session.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')
                        if table == 'parameters' and column == 'source':
                            session.execute("UPDATE parameters SET source='text' WHERE evidence<>''")

    def document_content(self, identity):
        with self() as session:
            row = session.execute('SELECT content FROM documents WHERE id=?', (identity,)).fetchone()
        if row is None:
            return None
        if row['content'] is not None:
            return bytes(row['content'])
        path = self.data / (identity + '.pdf')
        return path.read_bytes() if path.is_file() else None
