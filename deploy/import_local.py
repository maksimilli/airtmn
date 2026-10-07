"""Import a Windows data folder into an empty server volume, with validation."""
import sys
import tempfile
from pathlib import Path
from backup import create, restore

source, target = map(Path, sys.argv[1:])
with tempfile.TemporaryDirectory() as directory:
    archive = Path(directory) / 'local.tar.gz'
    create(source, archive)
    restore(target, archive)
print('Local catalog and PDFs imported')
