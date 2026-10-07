"""Select a compatible Python before creating the Windows environment."""
import os
from pathlib import Path
import subprocess
import sys
import webbrowser

PYTHON_DOWNLOAD = 'https://www.python.org/downloads/release/python-31210/'
VERSION_CHECK = 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) and sys.maxsize > 2**32 else 1)'


def compatible(command, runner=subprocess.run):
    try:
        return runner(command + ['-c', VERSION_CHECK], stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL).returncode == 0
    except OSError:
        return False


def start(root, runner=subprocess.run, open_browser=webbrowser.open):
    # Leave an incompatible previous environment and all user data untouched.
    legacy = root / '.venv-windows'
    environment = root / '.venv-windows-312'
    for existing in [legacy, environment]:
        executable = existing / 'Scripts' / 'python.exe'
        if executable.is_file() and compatible([str(executable)], runner):
            environment = existing
            break
    else:
        candidates = [[sys.executable], ['py', '-3.12']]
        local = os.environ.get('LOCALAPPDATA')
        if local:
            candidates.append([str(Path(local) / 'Programs' / 'Python' / 'Python312' / 'python.exe')])
        candidates.append(['python'])
        selected = next((command for command in candidates if compatible(command, runner)), None)
        if selected is None:
            print('This catalog needs Python 3.12 (64-bit) for OCR.', flush=True)
            print('Python 3.13/3.14 cannot install the current OCR library.', flush=True)
            print('Install Python 3.12 using "Windows installer (64-bit)" on:', flush=True)
            print(PYTHON_DOWNLOAD, flush=True)
            print('Keep "Python Launcher" selected. Then run START_WINDOWS.bat again.', flush=True)
            print('Your existing Python and the data folder can stay as they are.', flush=True)
            try:
                open_browser(PYTHON_DOWNLOAD)
            except OSError:
                pass
            return 1
        print('Preparing a Python 3.12 environment for the catalog...', flush=True)
        result = runner(selected + ['-m', 'venv', str(environment)])
        if result.returncode:
            return result.returncode
    executable = str(environment / 'Scripts' / 'python.exe')
    for script in ['install_dependencies.py', 'launch_windows.py']:
        result = runner([executable, str(root / script)], cwd=str(root))
        if result.returncode:
            return result.returncode
    return 0


if __name__ == '__main__':
    sys.exit(start(Path(__file__).resolve().parent))
