import fitz
import pytest
from app import ocr
from test_api import client, family_pdf


def raster_pdf(content):
    with fitz.open(stream=content,filetype='pdf') as source, fitz.open() as scan:
        for page in source:
            pix=page.get_pixmap(dpi=180,colorspace=fitz.csRGB,alpha=False)
            new=scan.new_page(width=page.rect.width,height=page.rect.height)
            new.insert_image(new.rect,stream=pix.tobytes('png'))
        return scan.tobytes(deflate=True)


def test_real_ocr_family_table_and_persisted_provenance(client):
    content=raster_pdf(family_pdf())
    with fitz.open(stream=content,filetype='pdf') as pdf:
        assert pdf[0].get_text().strip()==''
    data=client.post('/api/import',files={'file':('scan.pdf',content)}).json()
    assert data['ocr']['pages']==[1]
    assert [v['name'] for v in data['variants']]==['1N4001','1N4002']
    for variant,voltage in zip(data['variants'],[50,100]):
        assert {p['code']:p['value'] for p in variant['parameters']}=={'VRRM':voltage,'IF_AV':1}
        assert all(p['source']=='ocr' and 0<=p['confidence']<=1 for p in variant['parameters'])
    selected=data['variants'][0] | {'document_id':data['document_id']}
    identity=client.post('/api/components',json=selected).json()['id']
    stored=client.get(f'/api/components/{identity}').json()
    assert stored['parameters'][0]['source']=='ocr'
    assert stored['parameters'][0]['confidence']==data['variants'][0]['parameters'][0]['confidence']
    assert client.get('/api/documents/'+data['document_id']).content==content


def test_digital_document_bypasses_ocr_and_off_skips_scan(client,monkeypatch):
    def forbidden(page):
        pytest.fail('Digital text must not be sent to OCR in auto mode')
    monkeypatch.setattr(ocr,'recognize_page',forbidden)
    data=client.post('/api/import',files={'file':('digital.pdf',family_pdf())}).json()
    assert data['ocr']['pages']==[] and data['parameters']
    data=client.post('/api/import',data={'ocr_mode':'off'},files={'file':('scan.pdf',raster_pdf(family_pdf()))}).json()
    assert data['ocr']['pages']==[] and data['parameters']==[]
    assert client.post('/api/import',data={'ocr_mode':'invalid'},files={'file':('digital.pdf',family_pdf())}).status_code==422


def test_unavailable_ocr_explains_setup_and_retains_document(client,monkeypatch):
    monkeypatch.setattr(ocr,'status',lambda:{'available':False})
    content=raster_pdf(family_pdf())
    data=client.post('/api/import',files={'file':('scan.pdf',content)}).json()
    assert data['ocr']['skipped_pages']==[1]
    assert any('START_WINDOWS.bat' in warning for warning in data['warnings'])
    assert client.get('/api/documents/'+data['document_id']).content==content


def test_page_limit_preserves_indices_and_text_pages(client,monkeypatch):
    monkeypatch.setattr(ocr,'MAX_OCR_PAGES',1)
    monkeypatch.setattr(ocr,'status',lambda:{'available':True})
    def recognized(page):
        result=fitz.open(stream=family_pdf(),filetype='pdf')
        return result,[{'bbox':(0,0,600,800),'text':'test','confidence':.95}]
    monkeypatch.setattr(ocr,'recognize_page',recognized)
    with fitz.open(stream=raster_pdf(family_pdf()),filetype='pdf') as scanned, fitz.open(stream=family_pdf(),filetype='pdf') as digital, fitz.open() as source:
        source.insert_pdf(digital);source.insert_pdf(scanned);source.insert_pdf(scanned)
        content=source.tobytes(deflate=True)
    data=client.post('/api/import',files={'file':('mixed.pdf',content)}).json()
    assert data['ocr']['pages']==[2] and data['ocr']['skipped_pages']==[3]
    assert {p['page'] for p in data['parameters']}=={1,2}
    assert any('Разделите' in warning for warning in data['warnings'])


def test_failed_ocr_keeps_original_page_and_reports_reason(client,monkeypatch):
    monkeypatch.setattr(ocr,'status',lambda:{'available':True})
    def failed(page):raise RuntimeError('test failure')
    monkeypatch.setattr(ocr,'recognize_page',failed)
    data=client.post('/api/import',files={'file':('scan.pdf',raster_pdf(family_pdf()))}).json()
    assert data['ocr']['skipped_pages']==[1]
    assert any('test failure' in warning for warning in data['warnings'])


def test_manual_correction_clears_ocr_confidence(client):
    payload={'name':'CORRECTED','parameters':[{'code':'VF','value':1.1,'unit':'V','source':'manual','confidence':.7}]}
    identity=client.post('/api/components',json=payload).json()['id']
    stored=client.get(f'/api/components/{identity}').json()['parameters'][0]
    assert stored['source']=='manual' and stored['confidence'] is None


def test_windows_dependency_refresh_and_failed_install(tmp_path):
    import importlib.util
    from pathlib import Path
    from types import SimpleNamespace
    spec=importlib.util.spec_from_file_location('installer',Path(__file__).resolve().parents[2]/'install_dependencies.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    (tmp_path/'backend').mkdir();requirements=tmp_path/'backend'/'requirements.txt';requirements.write_text('first')
    calls=[]
    def successful(command):calls.append(command);return SimpleNamespace(returncode=0)
    assert module.install(tmp_path,successful)==0
    assert module.install(tmp_path,successful)==0 and len(calls)==1
    requirements.write_text('second')
    assert module.install(tmp_path,successful)==0 and len(calls)==2
    marker=tmp_path/'.venv-windows'/'installed.ok';previous=marker.read_text()
    requirements.write_text('third')
    assert module.install(tmp_path,lambda command:SimpleNamespace(returncode=1))==1
    assert marker.read_text()==previous
