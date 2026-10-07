import hashlib
import importlib.util
import io
import json
import sqlite3
import tarfile
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('catalog_backup',Path(__file__).resolve().parents[2]/'deploy'/'backup.py')
backup=importlib.util.module_from_spec(spec);spec.loader.exec_module(backup)


def test_backup_restore_preserves_database_and_pdf_and_refuses_overwrite(tmp_path):
    data=tmp_path/'data';data.mkdir()
    pdf=b'%PDF test original';identity=hashlib.sha256(pdf).hexdigest()
    (data/(identity+'.pdf')).write_bytes(pdf)
    with sqlite3.connect(data/'catalog.sqlite3') as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.execute('CREATE TABLE sessions(token TEXT)');c.execute("INSERT INTO sessions VALUES('old-session')");c.execute('CREATE TABLE documents(id TEXT)');c.execute('INSERT INTO documents VALUES(?)',(identity,));c.commit()
        archive=tmp_path/'backup.tar.gz'
        assert backup.create(data,archive)==2
    target=tmp_path/'restored'
    assert backup.restore(target,archive)==2
    assert (target/(identity+'.pdf')).read_bytes()==pdf
    with sqlite3.connect(target/'catalog.sqlite3') as c:
        assert c.execute('SELECT id FROM documents').fetchone()[0]==identity
        assert c.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]==0
    with pytest.raises(ValueError,match='empty'):
        backup.restore(target,archive)
    with pytest.raises(ValueError,match='already exists'):
        backup.create(data,archive)
    (data/(identity+'.pdf')).unlink()
    with pytest.raises(ValueError,match='missing'):
        backup.create(data,tmp_path/'missing.tar.gz')


@pytest.mark.parametrize('name',['../outside','/etc/passwd','extra.json'])
def test_restore_rejects_unexpected_paths_without_writing_data(tmp_path,name):
    archive=tmp_path/'bad.tar.gz'
    with tarfile.open(archive,'w:gz') as tar:
        entry=tarfile.TarInfo(name);entry.size=1;tar.addfile(entry,io.BytesIO(b'x'))
    target=tmp_path/'data'
    with pytest.raises(ValueError,match='Unexpected'):
        backup.restore(target,archive)
    assert not list(target.iterdir())


def test_restore_rejects_checksum_mismatch(tmp_path):
    archive=tmp_path/'bad.tar.gz'
    with tarfile.open(archive,'w:gz') as tar:
        for name,content in [('catalog.sqlite3',b'tampered'),('manifest.json',json.dumps({'format':1,'sha256':{'catalog.sqlite3':'0'*64}}).encode())]:
            entry=tarfile.TarInfo(name);entry.size=len(content);tar.addfile(entry,io.BytesIO(content))
    target=tmp_path/'data'
    with pytest.raises(ValueError,match='checksum'):
        backup.restore(target,archive)
    assert not list(target.iterdir())
