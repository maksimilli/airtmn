"""Start the bundled catalog and open it after the API is ready."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
import json

root = Path(__file__).resolve().parent
os.chdir(root)
url = 'http://127.0.0.1:8000'
with socket.socket() as sock:
    try:
        sock.bind(('127.0.0.1', 8000))
    except OSError:
        print('Port 8000 is busy. Close the previous catalog window and try again.')
        sys.exit(1)
process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--app-dir', 'backend', '--host', '127.0.0.1', '--port', '8000'])
try:
    for _ in range(60):
        if process.poll() is not None:
            raise RuntimeError('Server failed to start. See the error above.')
        try:
            with urllib.request.urlopen(url + '/api/health', timeout=1) as response:
                if json.load(response).get('status') == 'ok':
                    break
        except (OSError, ValueError):
            pass
        time.sleep(.5)
    else:
        raise RuntimeError('Server did not become ready within 30 seconds.')
    print('Catalog is ready: ' + url)
    print('Keep this window open. Press Ctrl+C to stop the catalog.')
    if os.getenv('CATALOG_NO_BROWSER') != '1':
        webbrowser.open(url)
    sys.exit(process.wait())
except KeyboardInterrupt:
    print('\nStopping catalog...')
except Exception as error:
    print(error)
    sys.exit(1)
finally:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
