import hashlib
import os
import math
import json
import time
from typing import Literal
from pathlib import Path

import fitz
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, TypeAdapter, ValidationError, model_validator
from app.parameters import DEFINITIONS, normalize
from app.categories import CATEGORIES, category_codes
from app.database import Database
from sqlalchemy.exc import IntegrityError

DATA = Path(os.getenv('CATALOG_DATA_DIR', 'data')).resolve()
DATA.mkdir(parents=True, exist_ok=True)
app = FastAPI(title='Каталог электронных компонентов')
app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:5173', 'http://127.0.0.1:5173'], allow_methods=['*'], allow_headers=['*'])


db = Database(DATA, os.getenv('DATABASE_URL', ''), os.getenv('CATALOG_DATABASE_PASSWORD_FILE', ''))
db.initialize()


from app.auth import install_auth
install_auth(app, db)


class Parameter(BaseModel):
    code: str
    value: float = Field(ge=0, allow_inf_nan=False)
    unit: str
    kind: Literal['min', 'typ', 'max', 'unspecified'] = 'max'
    conditions: str = ''
    page: int | None = Field(default=None, ge=1)
    evidence: str = ''
    source: Literal['text', 'ocr', 'manual'] = 'manual'
    confidence: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode='after')
    def normalize_value(self):
        self.value, self.unit = normalize(self.code, self.value, self.unit)
        if not math.isfinite(self.value):
            raise ValueError('Значение слишком большое')
        if self.source != 'ocr':
            self.confidence = None
        return self


class Component(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    manufacturer: str = ''
    package: str = ''
    description: str = ''
    document_id: str | None = None
    parameters: list[Parameter] = []
    category: str = 'diode'

    @model_validator(mode='after')
    def validate_category(self):
        if self.category not in CATEGORIES:
            raise ValueError('Неизвестная категория')
        if any(p.code not in category_codes(self.category) for p in self.parameters):
            raise ValueError('Характеристика не соответствует выбранной категории')
        return self


@app.get('/api/health')
def health():
    with db() as c:
        c.execute('SELECT 1')
    return {'status': 'ok', 'database': 'postgresql' if db.postgres else 'sqlite'}


@app.get('/api/ocr/status')
def ocr_status():
    from app.ocr import status
    return status()


@app.get('/api/parameter-definitions')
def parameter_definitions(category: str = 'diode'):
    if category not in CATEGORIES:
        raise HTTPException(422, 'Неизвестная категория')
    return [dict(code=code, **DEFINITIONS[code]) for code in category_codes(category)]


@app.get('/api/categories')
def categories():
    with db() as c:
        counts = dict(c.execute('SELECT category,COUNT(*) FROM components GROUP BY category').fetchall())
    return [dict(code=code, **definition, count=counts.get(code, 0)) for code, definition in CATEGORIES.items()]


@app.get('/api/stats')
def stats():
    with db() as c:
        return dict(components=c.execute('SELECT COUNT(*) FROM components').fetchone()[0],
                    documents=c.execute('SELECT COUNT(*) FROM documents').fetchone()[0],
                    manufacturers=c.execute("SELECT COUNT(DISTINCT manufacturer) FROM components WHERE manufacturer<>''").fetchone()[0],
                    parameters=c.execute('SELECT COUNT(*) FROM parameters').fetchone()[0])


def component_dict(connection, row):
    item = dict(row)
    item['parameters'] = [dict(p) for p in connection.execute(
        'SELECT * FROM parameters WHERE component_id=? ORDER BY id', (row['id'],))]
    return item


class ParameterFilter(BaseModel):
    model_config = {'extra': 'forbid'}
    code: str
    kind: Literal['min', 'typ', 'max', 'unspecified'] | None = None
    unit: str | None = None
    min: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    max: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    conditions: str = Field(default='', max_length=500)


@app.get('/api/components')
def components(q: str = '', min_voltage: float | None = None, min_current: float | None = None,
               manufacturer: str = '', package: str = '', parameter_code: str | None = None,
               parameter_kind: Literal['min', 'typ', 'max', 'unspecified'] = 'max',
               parameter_min: float | None = None, parameter_max: float | None = None,
               parameter_unit: str | None = None, conditions: str = '', category: str | None = None,
               filters: str | None = None):
    sql = 'SELECT * FROM components WHERE LOWER(name) LIKE LOWER(?) AND LOWER(manufacturer) LIKE LOWER(?) AND LOWER(package) LIKE LOWER(?)'
    args = ['%' + q + '%', '%' + manufacturer + '%', '%' + package + '%']
    if category is not None:
        if category not in CATEGORIES:
            raise HTTPException(422, 'Неизвестная категория')
        sql += ' AND category=?'
        args.append(category)
    for code, threshold in [('VRRM', min_voltage), ('IF_AV', min_current)]:
        if threshold is not None:
            if not math.isfinite(threshold) or threshold < 0:
                raise HTTPException(422, 'Граница фильтра должна быть конечным неотрицательным числом')
            sql += " AND EXISTS(SELECT 1 FROM parameters p WHERE p.component_id=components.id AND p.code=? AND p.kind='max' AND p.value>=?)"
            args.extend([code, threshold])
    active_filters = []
    if filters is not None:
        try:
            raw = json.loads(filters)
            if not isinstance(raw, list) or len(raw) > 20:
                raise ValueError('Добавьте не более 20 фильтров')
            active_filters = TypeAdapter(list[ParameterFilter]).validate_python(raw)
        except (ValueError, ValidationError) as error:
            raise HTTPException(422, f'Некорректные фильтры: {error}')
    if parameter_code:
        try:
            active_filters.append(ParameterFilter(code=parameter_code, kind=parameter_kind,
                unit=parameter_unit, min=parameter_min, max=parameter_max, conditions=conditions))
        except ValidationError as error:
            raise HTTPException(422, str(error))
    elif parameter_min is not None or parameter_max is not None or conditions:
        raise HTTPException(422, 'Выберите характеристику для дополнительного фильтра')
    for item in active_filters:
        definition = DEFINITIONS.get(item.code)
        if not definition:
            raise HTTPException(422, 'Неизвестная характеристика')
        try:
            unit = item.unit or definition['unit']
            normalize(item.code, 0, unit)
            lower = normalize(item.code, item.min, unit)[0] if item.min is not None else None
            upper = normalize(item.code, item.max, unit)[0] if item.max is not None else None
        except ValueError as error:
            raise HTTPException(422, str(error))
        if any(v is not None and (not math.isfinite(v) or v < 0) for v in [lower, upper]):
            raise HTTPException(422, 'Граница фильтра должна быть конечным неотрицательным числом')
        if lower is not None and upper is not None and lower > upper:
            raise HTTPException(422, 'Значение «от» не должно превышать «до»')
        clause = ' AND EXISTS(SELECT 1 FROM parameters p WHERE p.component_id=components.id AND p.code=?'
        args.append(item.code)
        if item.kind is not None:
            clause += ' AND p.kind=?'
            args.append(item.kind)
        if lower is not None:
            clause += ' AND p.value>=?'
            args.append(lower)
        if upper is not None:
            clause += ' AND p.value<=?'
            args.append(upper)
        if item.conditions:
            clause += ' AND LOWER(p.conditions) LIKE LOWER(?)'
            args.append('%' + item.conditions + '%')
        sql += clause + ')'
    with db() as c:
        return [component_dict(c, row) for row in c.execute(sql + ' ORDER BY name', args)]


@app.get('/api/components/{component_id}')
def get_component(component_id: int):
    with db() as c:
        row = c.execute('SELECT * FROM components WHERE id=?', (component_id,)).fetchone()
        if not row:
            raise HTTPException(404, 'Компонент не найден')
        return component_dict(c, row)


def save_component(component: Component, component_id: int | None = None):
    if not component.name.strip():
        raise HTTPException(422, 'Обозначение не может быть пустым')
    with db() as c:
        if component_id is not None and not c.execute('SELECT 1 FROM components WHERE id=?', (component_id,)).fetchone():
            raise HTTPException(404, 'Компонент не найден')
        if component.document_id and not c.execute('SELECT 1 FROM documents WHERE id=?', (component.document_id,)).fetchone():
            raise HTTPException(422, 'Документ не найден')
        values = (component.name.strip(), component.manufacturer.strip(), component.package.strip(),
                  component.description, component.document_id, component.category)
        try:
            if component_id is None:
                cursor = c.execute('INSERT INTO components(name,manufacturer,package,description,document_id,category) VALUES(?,?,?,?,?,?) RETURNING id', values)
                component_id = cursor.fetchone()[0]
            else:
                c.execute('UPDATE components SET name=?,manufacturer=?,package=?,description=?,document_id=?,category=? WHERE id=?', (*values, component_id))
                c.execute('DELETE FROM parameters WHERE component_id=?', (component_id,))
        except IntegrityError:
            raise HTTPException(409, 'Компонент этого производителя уже существует')
        for p in component.parameters:
            c.execute('INSERT INTO parameters(component_id,code,value,unit,kind,conditions,page,evidence,source,confidence) VALUES(?,?,?,?,?,?,?,?,?,?)',
                      (component_id, p.code, p.value, p.unit, p.kind, p.conditions, p.page, p.evidence, p.source, p.confidence))
        return {'id': component_id}


@app.post('/api/components', status_code=201)
def create(component: Component):
    return save_component(component)


@app.put('/api/components/{component_id}')
def update(component_id: int, component: Component):
    return save_component(component, component_id)


@app.delete('/api/components/{component_id}', status_code=204)
def delete_component(component_id: int):
    with db() as c:
        if not c.execute('DELETE FROM components WHERE id=?', (component_id,)).rowcount:
            raise HTTPException(404, 'Компонент не найден')


@app.get('/api/documents')
def documents():
    with db() as c:
        return [dict(row) for row in c.execute('''SELECT d.id,d.filename,d.pages,d.size, COUNT(c.id) AS components_count
            FROM documents d LEFT JOIN components c ON c.document_id=d.id
            GROUP BY d.id,d.filename,d.pages,d.size,d.created_at ORDER BY d.created_at DESC,d.id''')]


@app.get('/api/documents/{document_id}')
def document(document_id: str):
    from fastapi.responses import Response
    content = db.document_content(document_id)
    if content is None:
        raise HTTPException(404, 'Документ не найден')
    return Response(content, media_type='application/pdf')


@app.get('/api/documents/{document_id}/pages/{page_number}')
def document_page(document_id: str, page_number: int):
    from fastapi.responses import Response
    content = db.document_content(document_id)
    if content is None:
        raise HTTPException(404,'Документ не найден')
    try:
        with fitz.open(stream=content,filetype='pdf') as pdf:
            if page_number<1 or page_number>len(pdf):
                raise HTTPException(404,'Страница не найдена')
            page=pdf[page_number-1]
            scale=min(140/72,1800/max(page.rect.width,page.rect.height))
            image=page.get_pixmap(matrix=fitz.Matrix(scale,scale),colorspace=fitz.csRGB,alpha=False).tobytes('png')
        return Response(image,media_type='image/png',headers={'Cache-Control':'private, max-age=3600'})
    except (RuntimeError,ValueError,OSError):
        raise HTTPException(422,'Не удалось отобразить страницу PDF')


@app.post('/api/import')
def import_pdf(file: UploadFile = File(...), ocr_mode: Literal['auto', 'always', 'off'] = Form('auto'), category: str = Form('diode')):
    if category not in CATEGORIES:
        raise HTTPException(422, 'Неизвестная категория')
    content = file.file.read(20 * 1024 * 1024 + 1)
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(413, 'Максимальный размер PDF — 20 МБ')
    try:
        pdf = fitz.open(stream=content, filetype='pdf')
        if pdf.is_encrypted or len(pdf) > 200:
            pdf.close()
            raise HTTPException(422, 'Нужен PDF без пароля, не более 200 страниц')
    except (RuntimeError, ValueError):
        raise HTTPException(422, 'Не удалось прочитать PDF')
    from app.extraction import extract
    from app.ocr import prepare_document
    from app.classification import detect_category
    def check_category(pages):
        detected = detect_category(pages, filename=file.filename or '')
        if detected and category != 'other' and detected['category'] != category:
            raise HTTPException(422, dict(code='category_mismatch', message=f"В документе распознан другой тип компонента: {detected['label']}. Выберите соответствующий раздел или другой PDF.",
                                        expected_category=category, detected_category=detected['category'], detected_label=detected['label'], evidence=detected['evidence']))
        return detected
    page_count = len(pdf)
    with pdf:
        check_category([page.get_text() for page in pdf])
        original = extract(pdf, category=category, filename=file.filename or '')
        # Preserve the established digital-PDF path, including vector grids.
        protected = {p['page'] for v in original['variants'] for p in v['parameters']} | {p['page'] for p in original['parameters']}
        with prepare_document(pdf, ocr_mode, protected_pages=protected) as (prepared, records, ocr_info, ocr_warnings):
            extracted = extract(prepared, records, category=category, filename=file.filename or '') if records else original
    pages = extracted.pop('pages')
    detected = check_category(pages)
    warnings = extracted.pop('extraction_warnings') + ocr_warnings
    if not detected:
        warnings.append('Тип компонента не определён уверенно. Проверьте выбранную категорию по названию и описанию в PDF.')
    if ocr_info['pages']:
        warnings.append('OCR выполнен для страниц: ' + ', '.join(map(str, ocr_info['pages'])) + '. Проверьте по оригиналу модель, единицы и десятичные точки.')
    warnings.append('Проверьте обозначение компонента, предельные значения и условия измерения перед сохранением.')
    if len(extracted['variants']) > 1:
        warnings.append('Документ содержит несколько моделей: выберите нужную модель. Характеристики зависят от выбранной модели.')
    if not any(t.strip() for t in pages):
        warnings.append('Текст не найден. Включите OCR и проверьте читаемость скана; пустые страницы не содержат данных.')
    if not extracted['parameters']:
        warnings.append('Характеристики не удалось извлечь. Заполните их вручную.')
    digest = hashlib.sha256(content).hexdigest()
    with db() as c:
        duplicate = c.execute('SELECT 1 FROM documents WHERE id=?', (digest,)).fetchone() is not None
        c.execute('INSERT INTO documents(id,filename,pages,size,content,created_at) VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING',
            (digest, Path(file.filename or 'datasheet.pdf').name, page_count, len(content), content if db.postgres else None, int(time.time())))
        c.execute('UPDATE documents SET pages=?,size=? WHERE id=?', (page_count,len(content),digest))
        if not db.postgres:
            (DATA / (digest + '.pdf')).write_bytes(content)
    return dict(document_id=digest, duplicate=duplicate, ocr=ocr_info, category=category, detected_category=detected, filename=Path(file.filename or 'datasheet.pdf').name,
                page_count=page_count, **extracted, warnings=warnings, text_preview='\n'.join(pages)[:12000])

# A bundled frontend allows Windows users to run without Node.js.
from fastapi.staticfiles import StaticFiles
FRONTEND_DIST = Path(__file__).resolve().parents[2] / 'frontend' / 'dist'
if FRONTEND_DIST.is_dir():
    app.mount('/', StaticFiles(directory=FRONTEND_DIST, html=True), name='frontend')
