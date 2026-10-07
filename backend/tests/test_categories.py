import fitz
import pytest
from app import ocr
from test_api import client, family_pdf


def text_pdf(title, text):
    with fitz.open() as pdf:
        page=pdf.new_page(); page.insert_text((40,40),title+'\n'+text)
        return pdf.tobytes()


@pytest.mark.parametrize('category,title,text,expected',[
    ('mosfet','DEMO100 N-channel MOSFET','VDS = 100 V\nID = 5 A\nRDS(ON) = 20 mΩ',{'VDS':100,'ID':5,'RDS_ON':.02}),
    ('resistor','DEMO100 Resistor','R = 10 kohm\nPD = 250 mW\nTOL = 5 %',{'R':10000,'PD':.25,'TOL':5}),
    ('capacitor','DEMO100 Capacitor','C = 100 uF\nVRATED = 25 V\nESR = 0.1 ohm',{'C':.0001,'VRATED':25,'ESR':.1}),
    ('inductor','DEMO100 Inductor','L = 10 uH\nIRATED = 2 A',{'L':1e-5,'IRATED':2}),
])
def test_category_import_save_filters_and_units(client,category,title,text,expected):
    # Built-in PDF font lacks Omega; use the canonical ASCII spelling.
    text=text.replace('mΩ','mohm')
    data=client.post('/api/import',data={'category':category},files={'file':('spec.pdf',text_pdf(title,text))}).json()
    assert {p['code']:p['value'] for p in data['parameters']}==pytest.approx(expected)
    assert data['detected_category']['category']==category
    selected={key:data[key] for key in ['name','manufacturer','package','category','document_id','parameters']}
    assert client.post('/api/components',json=selected).status_code==201
    assert len(client.get('/api/components?category='+category).json())==1
    assert client.get('/api/components?category=diode').json()==[]


def test_wrong_category_blocks_before_document_is_saved(client):
    response=client.post('/api/import',data={'category':'resistor'},files={'file':('diode.pdf',family_pdf())})
    assert response.status_code==422
    assert response.json()['detail']['code']=='category_mismatch'
    assert response.json()['detail']['detected_category']=='diode'
    assert client.get('/api/documents').json()==[]
    assert client.get('/api/stats').json()['documents']==0


def test_aligned_table_without_grid_and_unit_before_value(client):
    with fitz.open() as pdf:
        page=pdf.new_page();page.insert_text((40,30),'MODEL100 N-channel MOSFET')
        xs=[40,220,300,420]
        for y,row in zip([80,110,140],[['PARAMETER','SYMBOL','UNIT','MAX'],['Drain voltage','VDS','V','100'],['Drain current','ID','A','5']]):
            for x,value in zip(xs,row):page.insert_text((x,y),value,fontsize=10)
        content=pdf.tobytes()
    data=client.post('/api/import',data={'category':'mosfet'},files={'file':('aligned.pdf',content)}).json()
    assert data['name']=='MODEL100'
    assert {p['code']:p['value'] for p in data['parameters']}=={'VDS':100,'ID':5}
    assert all(p['source']=='text' for p in data['parameters'])
    assert any('выравниванию' in w for w in data['warnings'])


def test_ocr_category_check_also_blocks_before_persistence(client,monkeypatch):
    from test_ocr import raster_pdf
    monkeypatch.setattr(ocr,'recognize_page',lambda page:(fitz.open(stream=family_pdf(),filetype='pdf'),[{'bbox':(0,0,600,800),'text':'diode','confidence':.9}]))
    response=client.post('/api/import',data={'category':'capacitor'},files={'file':('scan.pdf',raster_pdf(family_pdf()))})
    assert response.status_code==422 and response.json()['detail']['detected_category']=='diode'
    assert client.get('/api/documents').json()==[]


def test_unknown_type_warns_and_sparse_text_avoids_ocr(client,monkeypatch):
    def forbidden(page):pytest.fail('Recognized digital values must be retained')
    monkeypatch.setattr(ocr,'recognize_page',forbidden)
    with fitz.open() as pdf:
        page=pdf.new_page();page.insert_text((40,40),'DEMO100\nVF = 0.7 V');page.draw_line((40,100),(100,100))
        content=pdf.tobytes()
    result=client.post('/api/import',files={'file':('sparse.pdf',content)}).json()
    assert result['parameters'][0]['value']==.7 and result['parameters'][0]['source']=='text'
    assert result['ocr']['pages']==[]
    assert any('Тип компонента' in w for w in result['warnings'])


def test_documents_stats_export_delete_and_invalid_categories(client):
    result=client.post('/api/import',files={'file':('family.pdf',family_pdf())}).json()
    payload=result['variants'][0]|{'document_id':result['document_id']}
    payload['manufacturer']='=SUM(A1:A2)'
    identity=client.post('/api/components',json=payload).json()['id']
    document=client.get('/api/documents').json()[0]
    assert document['pages']==1 and document['size']>0 and document['components_count']==1
    preview=client.get('/api/documents/'+result['document_id']+'/pages/1')
    assert preview.status_code==200 and preview.content.startswith(b'\x89PNG')
    assert client.get('/api/documents/'+result['document_id']+'/pages/2').status_code==404
    assert client.get('/api/stats').json()=={'components':1,'documents':1,'manufacturers':1,'parameters':2}
    categories=client.get('/api/categories').json()
    assert len(categories)==10 and categories[0]['count']==1
    assert len(client.get('/api/parameter-definitions?category=resistor').json())==4
    exported=client.get('/api/components/export.csv?category=diode')
    assert exported.status_code==200 and "'=SUM(A1:A2)" in exported.text
    assert '1N4001' in exported.text and exported.content.startswith(b'\xef\xbb\xbf')
    assert client.get('/api/components?category=invalid').status_code==422
    assert client.post('/api/components',json={'name':'BAD','category':'resistor','parameters':[{'code':'VF','value':1,'unit':'V'}]}).status_code==422
    assert client.delete('/api/components/'+str(identity)).status_code==204
    assert client.get('/api/components/'+str(identity)).status_code==404
    assert client.get('/api/documents').json()[0]['components_count']==0
    assert client.get('/api/documents/'+result['document_id']).status_code==200
