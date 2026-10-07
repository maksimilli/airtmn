"""Local OCR with bundled RapidOCR models; no external binary or remote service."""
from contextlib import contextmanager
from functools import lru_cache
from importlib.util import find_spec
from threading import Lock

import fitz

DPI = 240
MAX_PIXELS = 12_000_000
MAX_OCR_PAGES = 10
_engine_lock = Lock()


def status():
    return {'available': all(find_spec(name) is not None for name in ['rapidocr_onnxruntime', 'onnxruntime', 'cv2', 'numpy']),
            'engine': 'RapidOCR', 'max_pages': MAX_OCR_PAGES}


@lru_cache(maxsize=1)
def engine():
    import onnxruntime
    onnxruntime.disable_telemetry_events()
    from rapidocr_onnxruntime import RapidOCR
    return RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1)


def needs_ocr(page):
    words = page.get_text('words')
    if len(words) >= 80:
        return False
    if not page.get_images() and not page.get_drawings():
        return False
    if len(words) < 10:
        return True
    # A scanned body can coexist with a short digital header or watermark.
    area = page.rect.width * page.rect.height
    return any(fitz.Rect(image['bbox']).get_area() > area * .6 for image in page.get_image_info())


def recognize_page(original):
    import cv2
    import numpy as np
    scale = DPI / 72
    if original.rect.width * original.rect.height * scale**2 > MAX_PIXELS:
        raise ValueError('страница слишком большая для OCR; уменьшите её до формата A4/A3')
    pix = original.get_pixmap(dpi=DPI, colorspace=fitz.csRGB, alpha=False)
    image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    with _engine_lock:
        result, _ = engine()(image, use_cls=True)
    document = fitz.open()
    page = document.new_page(width=pix.width / scale, height=pix.height / scale)
    records = []
    for box, text, confidence in result or []:
        text = text.replace('μ', 'µ').replace('℃', 'C').replace('Ω','ohm').replace('Ω','ohm')
        text = text.encode('cp1252', errors='replace').decode('cp1252')
        rect = fitz.Rect(min(p[0] for p in box)/scale, min(p[1] for p in box)/scale,
                         max(p[0] for p in box)/scale, max(p[1] for p in box)/scale)
        width = fitz.get_text_length(text, fontsize=1)
        size = min(rect.height * .6, rect.width / max(width, .001))
        if size <= 0 or not text.strip():
            continue
        page.insert_text((rect.x0, (rect.y0+rect.y1)/2 + size*.35), text, fontsize=size)
        records.append({'bbox': tuple(rect), 'text': text, 'confidence': float(confidence)})
    # Recreate original physical grid boundaries; never manufacture merged cells.
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    _, binary = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY_INV)
    horizontal_mask = cv2.morphologyEx(binary, cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (max(80, pix.width//25), 1)))
    vertical_mask = cv2.morphologyEx(binary, cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(20, pix.height//150))))
    # Inspect runs per column rather than contours: shaded heading bands
    # connect all vertical borders into one large component.
    accepted_vertical = np.zeros_like(vertical_mask)
    vertical_segments = {}
    minimum = max(20, pix.height//150)
    for x in range(pix.width):
        positions = (vertical_mask[:, x] > 0).astype(np.int8)
        transitions = np.diff(np.pad(positions, (1, 1)))
        starts, ends = np.flatnonzero(transitions == 1), np.flatnonzero(transitions == -1)
        for start, end in zip(starts, ends):
            if end-start < minimum:
                continue
            cross = horizontal_mask[max(0,start-5):min(pix.height,end+5), max(0,x-3):min(pix.width,x+4)]
            hits = np.any(cross > 0, axis=1).astype(np.int8)
            if np.sum(np.diff(np.pad(hits,(1,1))) == 1) < 2:
                continue
            accepted_vertical[start:end, x] = 255
            vertical_segments.setdefault((int(start), int(end)), []).append(x)
    shape = page.new_shape()
    for (start, end), columns in vertical_segments.items():
        groups = np.split(np.array(columns), np.flatnonzero(np.diff(columns) > 3)+1)
        for group in groups:
            x = float(np.mean(group))
            shape.draw_line((x/scale,start/scale),(x/scale,end/scale))
    for contour in cv2.findContours(horizontal_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
        x, y, width, height = cv2.boundingRect(contour)
        cross = accepted_vertical[max(0,y-5):min(pix.height,y+height+5),max(0,x-5):min(pix.width,x+width+5)]
        hits = np.any(cross > 0, axis=0).astype(np.int8)
        if np.sum(np.diff(np.pad(hits,(1,1))) == 1) < 2:
            continue
        ys = [y, y+height] if height > 6 else [y+height/2]
        for coordinate in ys:
            shape.draw_line((x/scale,coordinate/scale),((x+width)/scale,coordinate/scale))
    shape.finish(width=.2)
    shape.commit()
    return document, records


@contextmanager
def prepare_document(original, mode='auto', protected_pages=None):
    working = fitz.open()
    records, warnings, processed, skipped = {}, [], [], []
    attempted = 0
    try:
        for index, page in enumerate(original):
            wanted = mode != 'off' and (mode == 'always' or (index+1 not in (protected_pages or set()) and needs_ocr(page)))
            if wanted:
                if attempted >= MAX_OCR_PAGES:
                    warnings.append(f'Страница {index+1}: лимит OCR — {MAX_OCR_PAGES} страниц за импорт. Разделите большой скан на части.')
                    skipped.append(index+1)
                elif not status()['available']:
                    warnings.append(f'Страница {index+1}: OCR недоступен. Перезапустите START_WINDOWS.bat для установки зависимостей.')
                    skipped.append(index+1)
                else:
                    attempted += 1
                    try:
                        recognized, words = recognize_page(page)
                        try:
                            if not words:
                                raise ValueError('текст не распознан; проверьте качество и ориентацию скана')
                            working.insert_pdf(recognized)
                        finally:
                            recognized.close()
                        records[index+1] = words
                        processed.append(index+1)
                        continue
                    except (RuntimeError, ValueError, ImportError, OSError) as error:
                        warnings.append(f'Страница {index+1}: OCR не выполнен ({error}).')
                        skipped.append(index+1)
            working.insert_pdf(original, from_page=index, to_page=index)
        yield working, records, {'mode': mode, 'pages': processed, 'skipped_pages': skipped}, warnings
    finally:
        working.close()
