"""Conservative extraction of diode ratings from text and ruled family tables."""
import re

NUMBER = r'\d+(?:[.,]\d+)?'
PART = re.compile(r'(?=[A-Z0-9-]*[A-Z])(?=[A-Z0-9-]*\d)[A-Z0-9]+(?:-[A-Z0-9]+)*', re.I)


def parameter(code, value, unit, page, evidence, conditions=''):
    return dict(code=code, value=float(value.replace(',', '.')) / (1000 if unit.lower().startswith('m') else 1), unit='V' if code == 'VRRM' else 'A', kind='max', conditions=conditions, page=page, evidence=evidence, needs_review=True)


def extract(pdf):
    pages = [page.get_text() for page in pdf]
    text = '\n'.join(pages)
    manufacturer = 'Vishay' if re.search(r'\bVishay\b', pages[0] if pages else '', re.I) else ''
    case = re.search(r'Case:\s*([^\n,]+)', text, re.I)
    package = case.group(1).strip() if case else ''
    variants = {}
    common = []
    warnings = []
    for page_number, page in enumerate(pdf, 1):
        try:
            tables = page.find_tables().tables
        except (RuntimeError, ValueError):
            tables = []
            warnings.append(f'Не удалось разобрать таблицы на странице {page_number}.')
        for table in tables:
            rows = table.extract()
            heading = ' '.join(cell or '' for row in rows[:2] for cell in row)
            if not re.search(r'(maximum|absolute).*ratings', heading, re.I):
                continue
            header_index = next((i for i,r in enumerate(rows) if any((v or '').strip().upper() == 'SYMBOL' for v in r)), None)
            if header_index is None:
                continue
            header = rows[header_index]
            symbol_index = next(i for i,v in enumerate(header) if (v or '').strip().upper() == 'SYMBOL')
            columns = [(i, v.strip()) for i,v in enumerate(header) if i > symbol_index and v and PART.fullmatch(v.strip()) and table.rows[header_index].cells[i]]
            for row_index in range(header_index+1, len(rows)):
                row = rows[row_index]
                symbol = re.sub(r'\s+', '', row[symbol_index] or '').upper()
                code = {'VRRM':'VRRM', 'IF(AV)':'IF_AV', 'IF_AV':'IF_AV'}.get(symbol)
                if not code:
                    continue
                base = 'V' if code == 'VRRM' else 'A'
                unit = (row[-1] or '').strip()
                if unit not in {base, 'm'+base}:
                    continue
                for column, name in columns:
                    header_cell = table.rows[header_index].cells[column]
                    center = (header_cell[0]+header_cell[2])/2
                    # Read a physically merged cell only where it spans this model's column.
                    source = next((i for i,cell in enumerate(table.rows[row_index].cells) if i > symbol_index and i < len(row)-1 and cell and cell[0] <= center < cell[2]), None)
                    value = (row[source] or '').strip() if source is not None else ''
                    if not re.fullmatch(NUMBER, value):
                        continue
                    conditions = (row[0] or '').strip()
                    evidence = f'{name}: {conditions}; {symbol} = {value} {unit}'
                    variants.setdefault(name, []).append(parameter(code,value,unit,page_number,evidence,conditions))
        pattern = re.compile(r'\b(VRRM|IF\s*\(AV\)|IF_AV)\s*[:=]?\s*('+NUMBER+r')\s*(mA|A|mV|V)\b', re.I)
        for line in pages[page_number-1].splitlines():
            for match in pattern.finditer(line):
                symbol,value,unit = match.groups()
                code = 'VRRM' if symbol.upper() == 'VRRM' else 'IF_AV'
                if unit.upper().endswith('V' if code == 'VRRM' else 'A'):
                    common.append(parameter(code,value,unit,page_number,line))
    choices = [dict(name=name, manufacturer=manufacturer, package=package, description='', parameters=params) for name,params in variants.items()]
    # Never append unassigned text candidates to model-specific table values.
    selected = choices[0] if choices else dict(name='', manufacturer=manufacturer, package=package, description='', parameters=common)
    return dict(**selected, variants=choices, pages=pages, extraction_warnings=warnings)
