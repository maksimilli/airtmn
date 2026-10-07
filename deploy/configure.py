"""One-time configuration on the target server; never prints the password."""
import getpass
import os
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
if (root / '.env').exists():
    raise SystemExit('.env already exists. Existing settings will not be overwritten.')
domain = input('Domain, for example catalog.example.com: ').strip().lower()
if not re.fullmatch(r'(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,63}', domain):
    raise SystemExit('Enter a domain name without https://, port or path.')
username = input('Administrator login [admin]: ').strip().lower() or 'admin'
if not re.fullmatch(r'[a-z0-9][a-z0-9_.-]{2,39}', username):
    raise SystemExit('Login must contain 3–40 Latin letters, digits, dots, hyphens or underscores.')
password = getpass.getpass('Administrator password (at least 12 characters): ')
if not 12 <= len(password) <= 200 or password != getpass.getpass('Repeat password: '):
    raise SystemExit('Passwords must match and contain 12–200 characters.')
folder = root / 'deploy' / 'secrets'
folder.mkdir(exist_ok=True)
os.chmod(folder, 0o700)
secret = folder / 'admin_password'
# The private directory protects the host copy; read permission lets the non-root container read the secret.
fd = os.open(secret, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
with os.fdopen(fd, 'w', encoding='utf-8') as file:
    file.write(password + '\n')
os.chmod(secret, 0o444)
(root / '.env').write_text(f'CATALOG_DOMAIN={domain}\nCATALOG_ADMIN_USERNAME={username}\n', encoding='utf-8')
print('Configuration saved. Run: docker compose up -d --build')
