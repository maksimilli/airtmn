import hashlib
import os
import re
import sqlite3
from pathlib import Path

import fitz
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

DATA = Path(os.getenv('CATALOG_DATA_DIR', 'data')).resolve()
DATA.mkdir(parents=True, exist_ok=True)
app = FastAPI(title='Каталог электронных компонентов')
app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:5173', 'http://127.0.0.1:5173'], allow_methods=['*'], allow_headers=['*'])


def db():
    c = sqlite3.connect(DATA / 'catalog.sqlite3')
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c


with db() as c:
    c.executescript('''
    CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY, filename TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS components(
      id INTEGER PRIMARY KEY, name TEXT NOT NULL, manufacturer TEXT NOT NULL,
      package TEXT NOT NULL, description TEXT NOT NULL, document_id TEXT REFERENCES documents(id),
      UNIQUE(name, manufacturer));
    CREATE TABLE IF NOT EXISTS parameters(
      id INTEGER PRIMARY KEY, component_id INTEGER REFERENCES components(id) ON DELETE CASCADE,
      code TEXT NOT NULL, value REAL NOT NULL, unit TEXT NOT NULL,
      kind TEXT NOT NULL, conditions TEXT NOT NULL, page INTEGER, evidence TEXT NOT NULL);
    ''')


class Parameter(BaseModel):
    code: str
    value: float = Field(ge=0, allow_inf_nan=False)
    unit: str
    kind: str = 'max'
    conditions: str = ''
    page: int | None = Field(default=None, ge=1)
    evidence: str = ''


class Component(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    manufacturer: str = ''
    package: str = ''
    description: str = ''
    document_id: str | None = None
    parameters: list[Parameter] = []


@app.get('/api/health')
def health():
    return {'status': 'ok'}


@app.get('/api/components')
def components(q: str = '', min_voltage: float | None = None, min_current: float | None = None):
    sql = 'SELECT * FROM components WHERE name LIKE ?'
    args = ['%' + q + '%']
    for code, threshold in [('VRRM', min_voltage), ('IF_AV', min_current)]:
        if threshold is not None:
            sql += ' AND EXISTS(SELECT 1 FROM parameters p WHERE p.component_id=components.id AND p.code=? AND p.unit=? AND p.value>=?)'
            args.extend([code, 'V' if code == 'VRRM' else 'A', threshold])
    with db() as c:
        result = []
        for row in c.execute(sql + ' ORDER BY name', args):
            item = dict(row)
            item['parameters'] = [dict(p) for p in c.execute('SELECT * FROM parameters WHERE component_id=?', (row['id'],))]
            result.append(item)
        return result


@app.post('/api/components', status_code=201)
def create(component: Component):
    if not component.name.strip():
        raise HTTPException(422, 'Обозначение не может быть пустым')
    with db() as c:
        if component.document_id and not c.execute('SELECT 1 FROM documents WHERE id=?', (component.document_id,)).fetchone():
            raise HTTPException(422, 'Документ не найден')
        for p in component.parameters:
            if p.code not in {'VRRM', 'IF_AV'} or p.unit != ('V' if p.code == 'VRRM' else 'A') or p.kind != 'max':
                raise HTTPException(422, 'Поддерживаются предельные VRRM (V) и IF_AV (A)')
        try:
            cursor = c.execute('INSERT INTO components(name,manufacturer,package,description,document_id) VALUES(?,?,?,?,?)', (component.name.strip(), component.manufacturer.strip(), component.package, component.description, component.document_id))
        except sqlite3.IntegrityError:
            raise HTTPException(409, 'Компонент этого производителя уже существует')
        for p in component.parameters:
            c.execute('INSERT INTO parameters(component_id,code,value,unit,kind,conditions,page,evidence) VALUES(?,?,?,?,?,?,?,?)', (cursor.lastrowid,p.code,p.value,p.unit,p.kind,p.conditions,p.page,p.evidence))
        return {'id': cursor.lastrowid}


@app.get('/api/documents/{document_id}')
def document(document_id: str):
    from fastapi.responses import FileResponse
    with db() as c:
        row = c.execute('SELECT * FROM documents WHERE id=?', (document_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'Документ не найден')
    return FileResponse(DATA / (document_id + '.pdf'), media_type='application/pdf')


@app.post('/api/import')
async def import_pdf(file: UploadFile = File(...)):
    content = await file.read(20 * 1024 * 1024 + 1)
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(413, 'Максимальный размер PDF — 20 МБ')
    try:
        pdf = fitz.open(stream=content, filetype='pdf')
        if pdf.is_encrypted or len(pdf) > 200:
            pdf.close()
            raise HTTPException(422, 'Нужен PDF без пароля, не более 200 страниц')
    except (RuntimeError, ValueError):
        raise HTTPException(422, 'Не удалось прочитать PDF')
    parameters = []
    pages = []
    # Conservative first parser: only explicit symbols with one value and unit on a line.
    pattern = re.compile(r'\b(VRRM|IF\s*\(AV\)|IF_AV)\s*[:=]?\s*(\d+(?:[.,]\d+)?)\s*(mA|A|mV|V)\b', re.I)
    with pdf:
        for number, page in enumerate(pdf, 1):
            text = page.get_text()
            pages.append(text)
            for line in text.splitlines():
                for match in pattern.finditer(line):
                    symbol, value, unit = match.groups()
                    code = 'VRRM' if symbol.upper() == 'VRRM' else 'IF_AV'
                    base = 'V' if code == 'VRRM' else 'A'
                    if unit.upper().endswith(base):
                        parameters.append({'code':code, 'value':float(value.replace(',', '.')) / (1000 if unit.lower().startswith('m') else 1), 'unit':base, 'kind':'max', 'conditions':'', 'page':number, 'evidence':line, 'needs_review':True})
    digest = hashlib.sha256(content).hexdigest()
    with db() as c:
        duplicate = c.execute('SELECT 1 FROM documents WHERE id=?', (digest,)).fetchone() is not None
        c.execute('INSERT OR IGNORE INTO documents VALUES(?,?)', (digest, Path(file.filename or 'datasheet.pdf').name))
    (DATA / (digest + '.pdf')).write_bytes(content)
    return {'document_id':digest, 'duplicate':duplicate, 'name':'', 'manufacturer':'', 'package':'', 'parameters':parameters, 'warnings':['Проверьте обозначение компонента, предельные значения и условия измерения перед сохранением.'] + (['Текст не найден: сканированные PDF требуют OCR, который пока не подключён.'] if not any(t.strip() for t in pages) else []) + (['Поддерживаются только явно записанные VRRM и IF(AV). Остальные параметры заполните вручную.'] if not parameters else []), 'text_preview':'\n'.join(pages)[:6000]}

# A bundled frontend allows Windows users to run without Node.js.
from fastapi.staticfiles import StaticFiles
FRONTEND_DIST = Path(__file__).resolve().parents[2] / 'frontend' / 'dist'
if FRONTEND_DIST.is_dir():
    app.mount('/', StaticFiles(directory=FRONTEND_DIST, html=True), name='frontend')
