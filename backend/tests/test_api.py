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


def family_pdf(shared_current=True):
    """A ruled family table, with either a merged cell or a genuinely empty cell."""
    pdf = fitz.open()
    page = pdf.new_page()
    xs = [40, 220, 290, 380, 470, 550]
    ys = [50, 80, 110, 140, 170]
    for y in ys:
        page.draw_line((xs[0], y), (xs[-1], y))
    for x in [xs[0], xs[-1]]:
        page.draw_line((x,ys[0]), (x,ys[-1]))
    for x in xs[1:-1]:
        page.draw_line((x,ys[1]), (x,ys[3] if shared_current and x==xs[3] else ys[-1]))
    page.insert_text((45,70), 'MAXIMUM RATINGS', fontsize=9)
    rows = [
        ['PARAMETER','SYMBOL','1N4001','1N4002','UNIT'],
        ['Maximum reverse voltage','VRRM','50','100','V'],
        ['Current at TA = 75 C','IF(AV)','1.0','','A'],
    ]
    for i,row in enumerate(rows):
        for j,value in enumerate(row):
            page.insert_text((xs[j]+5,ys[i+1]+18), value, fontsize=8)
    content=pdf.tobytes()
    pdf.close()
    return content


def test_family_table_models_and_merged_current(client):
    data=client.post('/api/import', files={'file':('family.pdf',family_pdf())}).json()
    variants=data['variants']
    assert [v['name'] for v in variants]==['1N4001','1N4002']
    for v,voltage in zip(variants,[50,100]):
        assert {p['code']:p['value'] for p in v['parameters']}=={'VRRM':voltage,'IF_AV':1.0}
        assert all(p['page']==1 and v['name'] in p['evidence'] for p in v['parameters'])
        assert any('75' in p['conditions'] for p in v['parameters'] if p['code']=='IF_AV')
    selected=variants[1] | {'document_id':data['document_id']}
    assert client.post('/api/components',json=selected).status_code==201
    assert client.get('/api/components?min_voltage=100').json()[0]['name']=='1N4002'


def test_empty_cell_is_not_shared_with_other_model(client):
    data=client.post('/api/import', files={'file':('family.pdf',family_pdf(False))}).json()
    assert {p['code'] for p in data['variants'][0]['parameters']}=={'VRRM','IF_AV'}
    assert {p['code'] for p in data['variants'][1]['parameters']}=={'VRRM'}
