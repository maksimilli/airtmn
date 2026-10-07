"""Conservative text and ruled-table extraction with physical cell provenance."""
import re
from app.parameters import DEFINITIONS, RATING_CODES, normalize, symbol_code

NUMBER = r'\d+(?:[.,]\d+)?'
PART = re.compile(r'(?=[A-Z0-9-]*[A-Z])(?=[A-Z0-9-]*\d)[A-Z0-9]+(?:-[A-Z0-9]+)*', re.I)


def parameter(code, value, unit, page, evidence, conditions='', kind='max'):
    number, base_unit = normalize(code, float(value.replace(',', '.')), unit)
    return dict(code=code, value=number, unit=base_unit, kind=kind, conditions=conditions,
                page=page, evidence=evidence, needs_review=True, source='text', confidence=None)


def cell_at(table, rows, x, y):
    """Find the real cell covering a point, including vertically merged cells.

    An empty cell stays empty: previous-row values are never carried forward.
    """
    for row_index, row in enumerate(table.rows):
        for column, rect in enumerate(row.cells):
            if rect and rect[0] <= x < rect[2] and rect[1] <= y < rect[3]:
                return (rows[row_index][column] or '').strip()
    return ''


def row_y(row):
    # Shortest cells delimit this row when others merge vertically.
    cells = [rect for rect in row.cells if rect]
    return (max(rect[1] for rect in cells) + min(rect[3] for rect in cells)) / 2 if cells else None


def midpoint(rect):
    return (rect[0] + rect[2]) / 2


def infer_kind(description, heading, code):
    if re.match(r'\s*typical', description, re.I) or re.search(r'\b(typical|typ\.?)(?:\b|$)', description, re.I):
        return 'typ'
    if re.match(r'\s*minimum', description, re.I) or re.search(r'\b(minimum|min\.?)(?:\b|$)', description, re.I):
        return 'min'
    if re.match(r'\s*maximum', description, re.I) or re.search(r'\b(maximum|max\.?)(?:\b|$)', description, re.I):
        return 'max'
    if re.search(r'(maximum|absolute).*ratings', heading, re.I) and code in RATING_CODES:
        return 'max'
    return 'unspecified'


def description_code(description):
    """Match unambiguous electrical names when OCR loses a small symbol."""
    compact = re.sub(r'[^a-z]', '', description.lower())
    names = {'repetitivepeakreversevoltage': 'VRRM', 'rmsvoltage': 'VRMS',
             'dcblockingvoltage': 'VDC', 'averageforwardrectifiedcurrent': 'IF_AV',
             'peakforwardsurgecurrent': 'IFSM', 'forwardvoltage': 'VF',
             'dcreversecurrent': 'IR', 'junctioncapacitance': 'CJ',
             'reverserecoverytime': 'TRR', 'powerdissipation': 'PD'}
    matches = {code for name, code in names.items() if name in compact}
    return matches.pop() if len(matches) == 1 else ''


def confidence_at(table, x, y, records):
    rect = next((rect for row in table.rows for rect in row.cells
                 if rect and rect[0] <= x < rect[2] and rect[1] <= y < rect[3]), None)
    if not rect:
        return None
    scores = [record['confidence'] for record in records
              if rect[0] <= (record['bbox'][0]+record['bbox'][2])/2 < rect[2]
              and rect[1] <= (record['bbox'][1]+record['bbox'][3])/2 < rect[3]]
    return min(scores) if scores else None


def extract(pdf, ocr_records=None):
    ocr_records = ocr_records or {}
    pages = [page.get_text() for page in pdf]
    text = '\n'.join(pages)
    first_page = pages[0] if pages else ''
    manufacturer = next((name for name in ['Vishay', 'Nexperia', 'Diodes Incorporated', 'onsemi', 'STMicroelectronics']
                         if re.search(r'\b' + re.escape(name) + r'\b', first_page, re.I)), '')
    case = re.search(r'Case:\s*([^\n,]+)', text, re.I)
    package = case.group(1).strip() if case else ''
    variants, common, warnings = {}, [], []
    # A single explicitly titled device can receive min/typ/max table values.
    title_parts = PART.findall(first_page.splitlines()[0]) if first_page.splitlines() else []
    single_model = title_parts[0] if len(title_parts) == 1 else ''

    for page_number, page in enumerate(pdf, 1):
        try:
            tables = page.find_tables().tables
        except (RuntimeError, ValueError):
            tables = []
            warnings.append(f'Не удалось разобрать таблицы на странице {page_number}.')
        for table in tables:
            rows = table.extract()
            heading = ' '.join(cell or '' for row in rows[:2] for cell in row)
            if not re.search(r'ratings|characteristics', heading, re.I):
                continue
            header_index = next((i for i, row in enumerate(rows)
                                 if any((v or '').strip().upper() == 'SYMBOL' for v in row)), None)
            if header_index is None:
                continue
            header = rows[header_index]
            symbol_index = next(i for i, v in enumerate(header) if (v or '').strip().upper() == 'SYMBOL')
            unit_index = len(header) - 1
            headers = table.rows[header_index].cells
            columns = [(midpoint(headers[i]), v.strip(), None) for i, v in enumerate(header)
                       if i > symbol_index and v and PART.fullmatch(v.strip()) and headers[i]]
            # Explicit MIN/TYP/MAX headings override description-derived kinds.
            if not columns and single_model:
                columns = [(midpoint(headers[i]), single_model, v.strip().lower().rstrip('.'))
                           for i, v in enumerate(header) if i > symbol_index and v
                           and v.strip().lower().rstrip('.') in {'min', 'typ', 'max'} and headers[i]]
            if not columns:
                continue
            for row_index in range(header_index + 1, len(rows)):
                y = row_y(table.rows[row_index])
                if y is None or not headers[symbol_index]:
                    continue
                symbol = cell_at(table, rows, midpoint(headers[symbol_index]), y)
                code = symbol_code(symbol)
                description = cell_at(table, rows, midpoint(headers[0]), y) if headers[0] else ''
                inferred_symbol = False
                if code not in DEFINITIONS and page_number in ocr_records:
                    code = description_code(description)
                    inferred_symbol = code in DEFINITIONS
                    if inferred_symbol:
                        warnings.append(f'Страница {page_number}: символ {code} определён по описанию строки; проверьте по PDF.')
                if code not in DEFINITIONS:
                    continue
                unit = cell_at(table, rows, midpoint(headers[unit_index]), y) if headers[unit_index] else ''
                condition_parts = []
                # Sample each physical cell before SYMBOL; merged test cells are deduplicated.
                for col in range(1, symbol_index):
                    rect = table.rows[row_index].cells[col] or headers[col]
                    if rect:
                        value = cell_at(table, rows, midpoint(rect), y)
                        if value and value not in condition_parts:
                            condition_parts.append(value)
                # A merged description can contain a separate pulse duration per value row.
                pulse = r'tp\s*=\s*' + NUMBER + r'\s*(?:ns|µs|μs|ms|s)'
                if len(re.findall(pulse, description, re.I)) > 1:
                    cells = [rect for rect in table.rows[row_index].cells if rect]
                    top, bottom = max(rect[1] for rect in cells), min(rect[3] for rect in cells)
                    band = ' '.join(word[4] for word in page.get_text('words')
                                    if word[0] < headers[symbol_index][0] and top <= (word[1] + word[3]) / 2 < bottom)
                    duration = re.search(pulse, band, re.I)
                    if not duration:
                        warnings.append(f'Страница {page_number}: неоднозначные условия импульсного тока, строка пропущена.')
                        continue
                    description = re.sub(pulse, '', description, flags=re.I).strip() + '; ' + duration.group()
                context = heading.split('PARAMETER')[0].strip()
                context = re.sub(r'\(T(.*?)\)\s*A\b', r'(TA\1)', context, flags=re.S)
                # The default temperature does not override an explicit row temperature.
                if re.search(r'T[A-Z]?\s*=', ' '.join([description, *condition_parts]), re.I):
                    context = re.sub(r'\(.*?unless\s*otherwise\s*noted\)', '', context, flags=re.I|re.S).strip()
                    context = re.sub(r'\([^)]*T[A-Z]?\s*=[^)]*\)', '', context, flags=re.I).strip()
                conditions = '; '.join([context, description, *condition_parts])
                for center, name, explicit_kind in columns:
                    value = cell_at(table, rows, center, y)
                    if not re.fullmatch(NUMBER, value):
                        continue
                    kind = explicit_kind or infer_kind(description, heading, code)
                    evidence = f'{name}: {description}; {symbol or code} ({kind}) = {value} {unit}'
                    try:
                        item = parameter(code, value, unit, page_number, evidence, conditions, kind)
                    except ValueError:
                        continue
                    if page_number in ocr_records:
                        records = ocr_records[page_number]
                        scores = [confidence_at(table, x, point_y, records) for x, point_y in [
                            (center, y), (midpoint(headers[0] if inferred_symbol else headers[symbol_index]), y),
                            (midpoint(headers[unit_index]), y),
                            (center, row_y(table.rows[header_index]))]]
                        item['source'] = 'ocr'
                        item['confidence'] = min(score for score in scores if score is not None) if any(score is not None for score in scores) else None
                    variants.setdefault(name, []).append(item)
        pattern = re.compile(r'\b(VRRM|VRMS|VDC|IF\s*\(AV\)|IF_AV|IFSM|VF|IR|CJ|PD|TRR)\s*[:=]?\s*('
                             + NUMBER + r')\s*(µA|μA|uA|mA|A|mV|V|pF|nF|µF|μF|F|mW|W|ns|µs|μs|ms|s)\b', re.I)
        for line in pages[page_number - 1].splitlines():
            for match in pattern.finditer(line):
                symbol, value, unit = match.groups()
                code = symbol_code(symbol)
                # Keep ambiguous electrical text values unspecified until reviewed.
                kind = 'max' if code in RATING_CODES else infer_kind(line, '', code)
                try:
                    item = parameter(code, value, unit, page_number, line, kind=kind)
                    if page_number in ocr_records:
                        item['source'] = 'ocr'
                        scores = [record['confidence'] for record in ocr_records[page_number] if record['text'] in line]
                        item['confidence'] = min(scores) if scores else None
                    common.append(item)
                except ValueError:
                    continue
    choices = [dict(name=name, manufacturer=manufacturer, package=package, description='', parameters=params)
               for name, params in variants.items()]
    selected = choices[0] if choices else dict(name=single_model, manufacturer=manufacturer,
                                             package=package, description='', parameters=common)
    return dict(**selected, variants=choices, pages=pages, extraction_warnings=warnings)
