"""Start a hosted portal only after a PostgreSQL secret has been configured."""
import os
import sys

url = os.getenv('DATABASE_URL', '')
if not url.startswith(('postgres://', 'postgresql://', 'postgresql+psycopg://')):
    raise SystemExit('Add the PostgreSQL DATABASE_URL secret in your hosting settings, then restart.')
try:
    port = int(os.getenv('PORT', '7860'))
    if not 1 <= port <= 65535:
        raise ValueError()
except ValueError:
    raise SystemExit('PORT must be a number between 1 and 65535.')
os.execv(sys.executable, [sys.executable, '-m', 'uvicorn', 'app.main:app', '--app-dir', 'backend',
    '--host', '0.0.0.0', '--port', str(port), '--workers', '1',
    '--proxy-headers', '--forwarded-allow-ips', '*'])
