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


def test_edit_preserves_identity_and_document_and_conflicts_rollback(client):
    imported=client.post('/api/import',files={'file':('family.pdf',family_pdf())}).json()
    component=imported['variants'][0] | {'document_id':imported['document_id']}
    identity=client.post('/api/components',json=component).json()['id']
    second_id=client.post('/api/components',json={'name':'OTHER'}).json()['id']
    updated=component | {'description':'Updated', 'parameters':[
        {'code':'IR','value':5,'unit':'µA','kind':'max','conditions':'TA = 25 C','page':1,'evidence':'original'},
        {'code':'CJ','value':15,'unit':'pF','kind':'typ','conditions':'4 V, 1 MHz'},
    ]}
    assert client.put(f'/api/components/{identity}',json=updated).json()['id']==identity
    stored=client.get(f'/api/components/{identity}').json()
    assert stored['description']=='Updated' and stored['document_id']==imported['document_id']
    assert stored['parameters'][0]['value']==pytest.approx(5e-6)
    assert stored['parameters'][0]['unit']=='A' and stored['parameters'][0]['page']==1
    assert stored['parameters'][1]['value']==pytest.approx(15e-12)
    conflict=updated | {'name':'OTHER','manufacturer':''}
    assert client.put(f'/api/components/{identity}',json=conflict).status_code==409
    assert client.get(f'/api/components/{identity}').json()==stored
    assert client.get(f'/api/components/{second_id}').json()['name']=='OTHER'
    assert client.get('/api/components/999').status_code==404
    assert client.put('/api/components/999',json=updated).status_code==404


def test_parameter_filter_uses_same_value_kind_conditions_and_units(client):
    params=[
        {'code':'IR','value':5,'unit':'µA','kind':'max','conditions':'TA = 25 C'},
        {'code':'IR','value':50,'unit':'µA','kind':'max','conditions':'TA = 125 C'},
        {'code':'IR','value':1,'unit':'µA','kind':'typ','conditions':'TA = 125 C'},
        {'code':'VRRM','value':600,'unit':'V','kind':'typ'},
    ]
    assert client.post('/api/components',json={'name':'TEST','manufacturer':'Vishay','package':'DO-41','parameters':params}).status_code==201
    query='/api/components?parameter_code=IR&parameter_kind=max&parameter_unit=%C2%B5A&parameter_max=10'
    assert len(client.get(query).json())==1
    assert client.get(query+'&conditions=TA%20%3D%20125%20C').json()==[]
    assert len(client.get(query+'&conditions=TA%20%3D%2025%20C&manufacturer=Vish&package=DO').json())==1
    assert client.get(query+'&manufacturer=Other').json()==[]
    assert client.get('/api/components?min_voltage=500').json()==[]
    assert client.get(query+'&parameter_min=20').status_code==422
    assert client.get('/api/components?parameter_code=IR&parameter_unit=V').status_code==422
    assert client.get('/api/components?parameter_code=UNKNOWN').status_code==422


def min_typ_max_pdf():
    pdf=fitz.open(); page=pdf.new_page()
    page.insert_text((40,30),'TEST123')
    xs=[40,190,300,350,400,450,510,550]; ys=[50,80,110,140,170]
    for y in ys: page.draw_line((xs[0],y),(xs[-1],y))
    for x in [xs[0],xs[-1]]: page.draw_line((x,ys[0]),(x,ys[-1]))
    for x in xs[1:-1]: page.draw_line((x,ys[1]),(x,ys[-1]))
    page.insert_text((45,70),'ELECTRICAL CHARACTERISTICS')
    rows=[['PARAMETER','TEST CONDITIONS','SYMBOL','MIN','TYP','MAX','UNIT'],
          ['Forward voltage','IF = 1 A','VF','0.5','0.7','1.1','V'],
          ['Reverse current','TA = 25 C','IR','','2','5','uA']]
    for i,row in enumerate(rows):
        for j,value in enumerate(row):page.insert_text((xs[j]+4,ys[i+1]+18),value,fontsize=8)
    content=pdf.tobytes();pdf.close();return content


def test_explicit_min_typ_max_columns_and_blank_values(client):
    data=client.post('/api/import',files={'file':('test.pdf',min_typ_max_pdf())}).json()
    assert data['name']=='TEST123'
    params=data['parameters']
    assert [(p['code'],p['kind']) for p in params]==[('VF','min'),('VF','typ'),('VF','max'),('IR','typ'),('IR','max')]
    assert [p['value'] for p in params[:3]]==[.5,.7,1.1]
    assert all('IF = 1 A' in p['conditions'] for p in params[:3])
    assert params[-1]['value']==pytest.approx(5e-6)
    assert client.post('/api/components',json={key:data[key] for key in ['name','manufacturer','package','document_id','parameters']}).status_code==201


def test_units_and_kinds_validation(client):
    for parameter in [
        {'code':'IR','value':5,'unit':'V'},
        {'code':'CJ','value':-1,'unit':'pF'},
        {'code':'VF','value':1,'unit':'V','kind':'unknown'},
    ]:
        assert client.post('/api/components',json={'name':'BAD','parameters':[parameter]}).status_code==422
    assert client.get('/api/components').json()==[]


def test_startup_preserves_existing_database_and_files(tmp_path, monkeypatch):
    import sqlite3
    with sqlite3.connect(tmp_path/'catalog.sqlite3') as connection:
        connection.executescript('''
        CREATE TABLE documents(id TEXT PRIMARY KEY, filename TEXT NOT NULL);
        CREATE TABLE components(id INTEGER PRIMARY KEY, name TEXT NOT NULL, manufacturer TEXT NOT NULL,
          package TEXT NOT NULL, description TEXT NOT NULL, document_id TEXT REFERENCES documents(id), UNIQUE(name,manufacturer));
        CREATE TABLE parameters(id INTEGER PRIMARY KEY,component_id INTEGER REFERENCES components(id) ON DELETE CASCADE,
          code TEXT NOT NULL,value REAL NOT NULL,unit TEXT NOT NULL,kind TEXT NOT NULL,conditions TEXT NOT NULL,page INTEGER,evidence TEXT NOT NULL);
        INSERT INTO documents VALUES('legacy','legacy.pdf');
        INSERT INTO components VALUES(42,'LEGACY','Example','DO-41','Saved earlier','legacy');
        INSERT INTO parameters VALUES(12,42,'IF_AV',0.5,'A','max','TA = 75 C',1,'Source text');
        ''')
    (tmp_path/'legacy.pdf').write_bytes(b'%PDF legacy preserved file')
    monkeypatch.setenv('CATALOG_DATA_DIR',str(tmp_path))
    sys.modules.pop('app.main',None)
    module=importlib.import_module('app.main')
    with TestClient(module.app) as client:
        row=client.get('/api/components/42').json()
        assert row['name']=='LEGACY' and row['description']=='Saved earlier'
        assert row['parameters'][0]['value']==.5 and row['parameters'][0]['id']==12
        assert row['parameters'][0]['source']=='text' and row['parameters'][0]['confidence'] is None
        assert client.get('/api/documents/legacy').content==b'%PDF legacy preserved file'
        assert len(client.get('/api/components?min_current=0.5').json())==1
