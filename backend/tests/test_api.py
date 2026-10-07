import importlib
import sys
import fitz
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('CATALOG_DATA_DIR', str(tmp_path))
    sys.modules.pop('app.main', None)
    module = importlib.import_module('app.main')
    return TestClient(module.app)

def test_import_save_search_and_duplicate(client):
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((60,60), 'VRRM = 100 V\nIF(AV) = 500 mA')
    content = pdf.tobytes()
    pdf.close()
    result = client.post('/api/import', files={'file':('diode.pdf',content,'application/pdf')})
    assert result.status_code == 200
    draft = result.json()
    assert [(p['code'],p['value']) for p in draft['parameters']] == [('VRRM',100),('IF_AV',.5)]
    assert all(p['page'] == 1 and p['evidence'] for p in draft['parameters'])
    payload = {'name':'TEST100','manufacturer':'Example','document_id':draft['document_id'],'parameters':draft['parameters']}
    assert client.post('/api/components',json=payload).status_code == 201
    assert client.post('/api/components',json=payload).status_code == 409
    assert len(client.get('/api/components?q=TEST&min_voltage=100&min_current=0.5').json()) == 1
    assert client.get('/api/components?min_current=1').json() == []
    assert client.get('/api/documents/'+draft['document_id']).content == content
    assert client.post('/api/import',files={'file':('diode.pdf',content)}).json()['duplicate']

def test_invalid_pdf_and_parameter(client):
    assert client.post('/api/import',files={'file':('bad.pdf',b'not pdf')}).status_code == 422
    assert client.post('/api/components',json={'name':'x','parameters':[{'code':'VRRM','value':2,'unit':'A'}]}).status_code == 422

def test_scan_reports_missing_text(client):
    pdf=fitz.open(); pdf.new_page(); content=pdf.tobytes(); pdf.close()
    response=client.post('/api/import',files={'file':('scan.pdf',content)}).json()
    assert response['parameters'] == []
    assert any('OCR' in w for w in response['warnings'])
