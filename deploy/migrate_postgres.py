"""Optional transfer of an existing local catalog to an EMPTY PostgreSQL database."""
import argparse
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.database import Database
from app.transfer import copy_sqlite

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path('data'))
    args = parser.parse_args()
    url = os.getenv('DATABASE_URL') or getpass.getpass('PostgreSQL connection URL (hidden): ')
    target = Database(args.source, url, os.getenv('CATALOG_DATABASE_PASSWORD_FILE', ''))
    try:
        if not target.postgres:
            raise SystemExit('A PostgreSQL target is required')
        counts = copy_sqlite(args.source, target)
        print('Catalog imported:', ', '.join(f'{name}={count}' for name, count in counts.items()))
        print('Source unchanged. Sessions were not transferred; sign in again.')
    finally:
        target.engine.dispose()
