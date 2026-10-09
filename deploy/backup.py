"""Create or restore a portable backup while the application is stopped."""
import argparse
from contextlib import closing
import hashlib
import json
import re
import sqlite3
import tarfile
import tempfile
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))

ALLOWED = re.compile(r'(catalog\.sqlite3|[0-9a-f]{64}\.pdf)\Z')


def create(data: Path, output: Path, database_url: str = ''):
    if database_url:
        from app.database import Database
        from app.transfer import snapshot_postgres
        source = Database(data, database_url, os.getenv('CATALOG_DATABASE_PASSWORD_FILE', ''))
        try:
            if not source.postgres:
                raise ValueError('Remote backups require a PostgreSQL URL')
            with tempfile.TemporaryDirectory() as directory:
                snapshot = Path(directory)
                snapshot_postgres(source, snapshot)
                return create(snapshot, output)
        finally:
            source.engine.dispose()
    if output.exists():
        raise ValueError('Backup already exists; choose a new filename')
    database = data / 'catalog.sqlite3'
    if not database.is_file():
        raise ValueError('Catalog database not found')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        staging = Path(temp)
        with closing(sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True)) as source:
            with closing(sqlite3.connect(staging / 'catalog.sqlite3')) as target:
                source.backup(target)
                if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('SQLite integrity check failed')
                document_ids = [row[0] for row in target.execute('SELECT id FROM documents')]
        for identity in document_ids:
            if not re.fullmatch(r'[0-9a-f]{64}', identity) or not (data / (identity + '.pdf')).is_file():
                raise ValueError('A document referenced by the database is missing')
        files = [staging / 'catalog.sqlite3'] + sorted(data.glob('*.pdf'))
        files = [path for path in files if ALLOWED.fullmatch(path.name)]
        manifest = {'format': 1, 'created_utc': datetime.now(timezone.utc).isoformat(),
                    'sha256': {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in files}}
        (staging / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        pending = output.with_name(output.name + '.partial')
        try:
            with tarfile.open(pending, 'w:gz') as archive:
                for path in files + [staging / 'manifest.json']:
                    archive.add(path, arcname=path.name, recursive=False)
            pending.replace(output)
        finally:
            pending.unlink(missing_ok=True)
    return len(files)


def restore(data: Path, archive_path: Path, database_url: str = ''):
    if database_url:
        from app.database import Database
        from app.transfer import copy_sqlite
        target = Database(data, database_url, os.getenv('CATALOG_DATABASE_PASSWORD_FILE', ''))
        try:
            if not target.postgres:
                raise ValueError('Remote restores require a PostgreSQL URL')
            with tempfile.TemporaryDirectory() as directory:
                snapshot = Path(directory)
                count = restore(snapshot, archive_path)
                copy_sqlite(snapshot, target)
                return count
        finally:
            target.engine.dispose()
    data.mkdir(parents=True, exist_ok=True)
    if any(data.iterdir()):
        raise ValueError('Restore requires an empty data directory; existing data will not be overwritten')
    with tempfile.TemporaryDirectory(prefix=".restore-", dir=data) as temp:
        staging = Path(temp)
        with tarfile.open(archive_path, 'r:gz') as archive:
            names = set()
            for member in archive:
                if (not member.isfile() or member.name in names or
                    not (member.name == 'manifest.json' or ALLOWED.fullmatch(member.name))):
                    raise ValueError('Unexpected or duplicate archive entry')
                names.add(member.name)
                with archive.extractfile(member) as source, (staging / member.name).open('wb') as target:
                    while chunk := source.read(1024 * 1024):
                        target.write(chunk)
        manifest = json.loads((staging / 'manifest.json').read_text(encoding='utf-8'))
        expected = manifest.get('sha256', {})
        if manifest.get('format') != 1 or set(expected) != names - {'manifest.json'} or 'catalog.sqlite3' not in expected:
            raise ValueError('Invalid backup manifest')
        for name, digest in expected.items():
            if hashlib.sha256((staging / name).read_bytes()).hexdigest() != digest:
                raise ValueError('Backup checksum mismatch')
        with closing(sqlite3.connect((staging / 'catalog.sqlite3').as_uri() + '?mode=ro', uri=True)) as connection:
            if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('SQLite integrity check failed')
            for identity, in connection.execute('SELECT id FROM documents'):
                if not re.fullmatch(r'[0-9a-f]{64}', identity) or identity + '.pdf' not in expected:
                    raise ValueError('Referenced document missing from backup')
        # A restored backup must not reactivate browser sessions that were revoked later.
        with closing(sqlite3.connect(staging / 'catalog.sqlite3')) as connection:
            connection.execute('PRAGMA journal_mode=DELETE')
            with connection:
                if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='sessions'").fetchone():
                    connection.execute('DELETE FROM sessions')
        for name in expected:
            (staging / name).replace(data / name)
    return len(expected)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['create', 'restore'])
    parser.add_argument('--data', type=Path, default=Path('/data'))
    parser.add_argument('--archive', type=Path, required=True)
    args = parser.parse_args()
    count = globals()[args.action](args.data, args.archive, os.getenv('DATABASE_URL', ''))
    print(f'{args.action}: {count} files verified')
