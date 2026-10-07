"""Reset an existing administrator password from the server console."""
import getpass
import os
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.auth import password_hash

username = (sys.argv[1] if len(sys.argv) > 1 else 'admin').strip().lower()
password = getpass.getpass('New administrator password: ')
if not 12 <= len(password) <= 200 or password != getpass.getpass('Repeat password: '):
    raise SystemExit('Passwords must match and contain 12–200 characters.')
path = Path(os.getenv('CATALOG_DATA_DIR', '/data')) / 'catalog.sqlite3'
with sqlite3.connect(path.resolve().as_uri() + '?mode=rw', uri=True) as connection:
    row = connection.execute("SELECT id FROM users WHERE username=? AND role='admin'", (username,)).fetchone()
    if not row:
        raise SystemExit('Administrator account not found')
    connection.execute('UPDATE users SET password_hash=?,enabled=1 WHERE id=?', (password_hash(password),row[0]))
    connection.execute('DELETE FROM sessions WHERE user_id=?', (row[0],))
print('Password reset. Existing sessions revoked.')
