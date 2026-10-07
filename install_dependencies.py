"""Refresh Windows dependencies only when requirements or Python change."""
import hashlib
import subprocess
import sys
from pathlib import Path


def install(root, runner=subprocess.run, environment=None):
    if sys.version_info[:2] != (3, 12) or sys.maxsize <= 2**32:
        print('OCR requires Python 3.12 (64-bit). Run START_WINDOWS.bat to select it.', flush=True)
        return 1
    requirements = root / 'backend' / 'requirements.txt'
    marker = (environment or root / '.venv-windows') / 'installed.ok'
    fingerprint = hashlib.sha256(requirements.read_bytes() + str(sys.version_info[:2]).encode()).hexdigest()
    if marker.exists() and marker.read_text().strip() == fingerprint:
        return 0
    print('Installing/updating dependencies and local OCR models. Internet access is required.', flush=True)
    result = runner([sys.executable, '-m', 'pip', 'install', '-r', str(requirements)])
    if result.returncode:
        return result.returncode
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(fingerprint)
    print('Dependencies are ready.', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(install(Path(__file__).resolve().parent, environment=Path(sys.prefix)))
