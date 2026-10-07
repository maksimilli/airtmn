"""Read electrical tables from physical word positions, including unruled tables.

Numbers are accepted only in explicit value columns or labeled specifications.
Catalog rows stay tied to a part number; application circuits and plots are excluded.
"""

import re
from app.parameters import DEFINITIONS, symbol_code, canonical_unit
from app.categories import category_codes

NUM = r"(?:\d+(?:[.,]\d+)?|[.,]\d+)(?:[eE][+-]?\d+)?"
MANUFACTURERS = [
    "Texas Instruments",
    "Silicon Laboratories",
    "STMicroelectronics",
    "Panasonic",
    "Nicomatic",
    "NXP",
    "Murata",
    "Samtec",
    "Nexperia",
    "Vishay",
    "Traco",
    "Pulse",
    "TE Connectivity",
    "TDK",
    "FCI",
    "onsemi",
    "Para Light",
]
NAMES = [
    (r"^(?:operating )?supply voltage|^power supply voltage", "VCC"),
    (r"^supply current|^quiescent (?:supply )?current|^current consumption", "ICC"),
    (r"^input voltage(?:\s+range)?(?:$|\s*[,([]|\s+VIN\b)", "VIN"),
    (r"^output voltage(?:\s+range)?(?:$|\s*[,([]|\s+VOUT\b)", "VOUT"),
    (r"^output current|^maximum output current", "IOUT"),
    (r"^continuous reverse voltage|^reverse voltage", "VR"),
    (r"^continuous forward current|^forward current", "IF"),
    (r"^forward voltage", "VF"),
    (r"^reverse (?:leakage )?current", "IR"),
    (r"^diode capacitance|^junction capacitance", "CJ"),
    (r"^reverse recovery time", "TRR"),
    (r"^breakdown voltage", "VBR"),
    (r"^clamping voltage", "VCL"),
    (r"^peak pulse current", "IPP"),
    (r"^power dissipation|^total power dissipation", "PD"),
    (r"^gain.bandwidth product|^bandwidth", "GBW"),
    (r"^slew rate", "SR"),
    (r"^rated voltage", "VRATED"),
    (r"^rated capacitance|^capacitance$", "C"),
    (r"^rated current|^current rating", "IRATED"),
    (r"^(?:switching |clock |operating )?frequency|^output data rate", "FREQ"),
    (r"^NO\.?\s*(?:OF)?\s*CONTACTS|^Number of contacts", "PINS"),
    (r"^contact resistance", "CONTACT_R"),
    (r"^inductance", "L"),
    (r"^DC resistance|^DCR", "DCR"),
    (r"^impedance", "Z"),
    (r"^LC", "IR"),
    (r"^ESR", "ESR"),
    (r"^Maximum allowable ripple current", "IRIPPLE"),
    (r"^efficiency", "EFF"),
    (r"^output power", "POUT"),
]


def words(page):
    # Some old TI sheets print glyphs twice for bold type. Deduplicate physical
    # words before reconstructing rows, rather than changing the PDF itself.
    result = []
    seen = set()
    for word in page.get_text("words"):
        key = (round(word[0]), round(word[1]), word[4])
        if key not in seen:
            result.append(word)
            seen.add(key)
    return sorted(result, key=lambda w: (w[1], w[0]))


def lines(items, tolerance=2.5):
    groups = []
    for w in sorted(items, key=lambda w: ((w[1] + w[3]) / 2, w[0])):
        y = (w[1] + w[3]) / 2
        if groups and abs(y - groups[-1][0]) <= tolerance:
            groups[-1][1].append(w)
        else:
            groups.append([y, [w]])
    return [(y, sorted(ws, key=lambda w: w[0])) for y, ws in groups]


def joined(items):
    return " ".join(w[4] for w in sorted(items, key=lambda w: (round(w[1] / 3), w[0])))


def metadata(pages, filename):
    first = pages[0] if pages else ""
    name = ""
    # A filename hints at an ordering code only when that code occurs in the PDF.
    hint = (
        re.sub(r"\.pdf$", "", filename, flags=re.I)
        .split("_", 1)[-1]
        .strip()
        .rstrip("_")
    )
    compact = "\n".join(pages).upper()
    if (
        hint
        and re.search(r"\d", hint)
        and len(hint) >= 4
        and re.search(
            r"(?<![A-Z0-9])" + re.escape(hint.upper()) + r"(?=[A-Z]*(?:[^A-Z0-9]|$))",
            compact,
        )
    ):
        name = hint.upper()
    if not name:
        for line in first.splitlines()[:35]:
            candidates = re.findall(
                r"\b(?:SN\d[A-Z0-9]+|TPS\d[A-Z0-9-]*|TMS320[A-Z0-9]+|OPA\d+|LP\d+|LMZ\d+[A-Z]*|SI\d+[A-Z0-9-]*|BAT\d+[A-Z]*|74LVC\d+[A-Z]*|ST8R\w+|L3GD\w+|NC7\w+)\b",
                line,
                re.I,
            )
            if candidates:
                name = candidates[0].upper()
                break
    normalized = (first + "\n" + filename).replace("_", " ").replace("-", " ").lower()
    manufacturer = next(
        (m for m in MANUFACTURERS if m.lower().replace("-", " ") in normalized), ""
    )
    if not manufacturer and "on semiconductor" in normalized:
        manufacturer = "onsemi"
    if not manufacturer and "st microelectronics" in normalized:
        manufacturer = "STMicroelectronics"
    return name, manufacturer


def row_code(items, supported, left, symbol_right, symbol_left=0):
    leading = [w for w in items if w[0] < left]
    # A symbol must be at the beginning of a row, not in its test conditions.
    for w in (leading if symbol_left else leading[:2]):
        if w[0] > symbol_right or w[0] < symbol_left:
            continue
        code = symbol_code(w[4].strip(",:"))
        if code in supported:
            return code
    description = joined(leading).strip()
    if not leading or leading[0][0] > symbol_right:
        return ""
    description = (
        re.sub(r"^[A-Z][A-Za-z0-9()_-]{0,15}\s+(?=[A-Za-z])", "", description)
        if leading
        and leading[0][4].isupper()
        and symbol_code(leading[0][4]) not in supported
        else description
    )
    for pattern, code in NAMES:
        if code in supported and re.search(pattern, description, re.I):
            return code
    return ""


def table_parameters(page, page_number, category, make_parameter):
    ws = words(page)
    missing = [
        c["bbox"]
        for b in page.get_text("rawdict")["blocks"]
        for l in b.get("lines", [])
        for span in l["spans"]
        for c in span["chars"]
        if c["c"] == "\x00"
    ]
    supported = set(category_codes(category))
    grouped = lines(ws)
    out = []
    for index, (hy, header) in enumerate(grouped):
        columns = [
            (
                w,
                (w[0] + w[2]) / 2,
                (
                    re.sub(r"[^a-z]", "", w[4].lower()).removesuffix("t")
                    if w[4].upper() == "TYPT"
                    else re.sub(r"[^a-z]", "", w[4].lower())
                ),
            )
            for w in header
            if re.sub(r"[^A-Z]", "", w[4].upper()) in {"MIN", "TYP", "MAX", "TYPT"}
        ]
        units = [w for w in header if w[4].upper() in {"UNIT", "UNITS"}]
        if columns and not units:
            last = max(x for _, x, _ in columns)
            candidates = [w for w in header if (w[0] + w[2]) / 2 > last + 15]
            for w in candidates:
                cx = (w[0] + w[2]) / 2
                printed = [
                    v
                    for v in ws
                    if hy + 5 < (v[1] + v[3]) / 2 < hy + 260
                    and abs((v[0] + v[2]) / 2 - cx) < 20
                    and canonical_unit(v[4])
                    in {u for code in supported for u in DEFINITIONS[code]["units"]}
                ]
                if len(printed) >= 2:
                    units = [w]
                    break
        if not columns or not units:
            continue
        columns.sort(key=lambda x: x[1])
        ux = (units[-1][0] + units[-1][2]) / 2
        vx = columns[0][1]
        if ux <= vx:
            continue
        boundaries = [vx - (columns[1][1] - vx) / 2 if len(columns) > 1 else vx - 25]
        boundaries += [
            (columns[i][1] + columns[i + 1][1]) / 2 for i in range(len(columns) - 1)
        ]
        boundaries += [(columns[-1][1] + ux) / 2]
        section = joined([w for w in ws if hy - 55 < (w[1] + w[3]) / 2 < hy - 5])
        # Exclude timing plots and function/pin tables that happen to contain MAX.
        if not re.search(
            r"characteristic|rating|operating|electrical|specification|supply|parameter",
            section + " " + joined(header),
            re.I,
        ):
            continue
        end = next(
            (
                y - 3
                for y, row in grouped[index + 1 :]
                if any(w[4].upper() in {"UNIT", "UNITS"} for w in row)
                and any(
                    re.sub(r"[^A-Z]", "", w[4].upper()) in {"MIN", "TYP", "MAX", "TYPT"}
                    for w in row
                )
            ),
            page.rect.height - 30,
        )
        symbol_headers = [
            w for w in header if w[4].lower() in {"symbol", "parameter", "parameters"}
        ]
        symbol_left = min(
            (w[0] - 5 for w in header if w[4].lower() == "symbol"), default=0
        )
        condition_headers = [
            w for w in header if w[4].upper() in {"TEST", "CONDITIONS"}
        ]
        symbol_right = (
            (min(w[0] for w in symbol_headers) + 45)
            if any(w[4].lower() == "symbol" for w in symbol_headers)
            else min(
                (w[0] - 5 for w in condition_headers), default=page.rect.width * 0.32
            )
        )
        horizontals = []
        for drawing in page.get_drawings():
            for shape in drawing["items"]:
                if shape[0] == "l" and abs(shape[1].y - shape[2].y) < 0.6:
                    horizontals.append(
                        (
                            min(shape[1].x, shape[2].x),
                            max(shape[1].x, shape[2].x),
                            shape[1].y,
                        )
                    )
                elif shape[0] == "re":
                    horizontals.extend(
                        [
                            (shape[1].x0, shape[1].x1, shape[1].y0),
                            (shape[1].x0, shape[1].x1, shape[1].y1),
                        ]
                    )
        body = [w for w in ws if hy + 4 < (w[1] + w[3]) / 2 < end]
        rows = lines(body)
        code = ""
        description = ""
        previous_unit = ""
        active_y = hy
        symbol_rows = [
            (y, r)
            for y, r in rows
            if r
            and r[0][0] <= symbol_right
            and re.fullmatch(r"[A-Za-z∆?][A-Za-z0-9_()/?-]{0,15}", r[0][4].strip(",:"))
            and len(r) > 1
        ]
        for y, row in rows:
            ahead = next((r for sy, r in symbol_rows if 0 < sy - y < 10), None)
            if ahead:
                code = row_code(
                    ahead, supported, boundaries[0], symbol_right, symbol_left
                )
                description = joined([w for w in ahead if w[0] < boundaries[0]])
                previous_unit = ""
                active_y = y
            candidate = row_code(
                row, supported, boundaries[0], symbol_right, symbol_left
            )
            leading = [w for w in row if w[0] < boundaries[0]]
            # Clear context for an unsupported new symbol or a new section.
            if leading and (
                candidate
                or (
                    re.fullmatch(
                        r"[A-Za-z∆?][A-Za-z0-9_()/?-]{0,15}", leading[0][4].strip(",:")
                    )
                    and leading[0][0] <= symbol_right
                    and len(leading) > 1
                )
            ):
                if candidate != code:
                    previous_unit = ""
                code = candidate
                description = joined(leading)
                active_y = y
            # Real horizontal boundaries recover a centered/merged symbol even
            # when its first numeric row precedes the symbol in reading order.
            anchor = min((w[0] for _, r in symbol_rows for w in r[:1]), default=0)
            cuts = sorted(
                {h for x0, x1, h in horizontals if x0 <= anchor <= x1 and hy < h < end}
            )
            top = max((h for h in cuts if h < y), default=hy)
            bottom = min((h for h in cuts if h > y), default=end)
            border_symbol = next(
                (
                    w
                    for w in body
                    if abs(w[0] - anchor) < 8
                    and (
                        abs((w[1] + w[3]) / 2 - top) < 2
                        or abs((w[1] + w[3]) / 2 - bottom) < 2
                    )
                    and symbol_code(w[4]) in supported
                ),
                None,
            )
            if border_symbol:
                sy = (border_symbol[1] + border_symbol[3]) / 2
                top = max((h for h in cuts if h < sy - 2), default=hy)
                bottom = min((h for h in cuts if h > sy + 2), default=end)
            if bottom - top < 150 and len(cuts) > 2:
                labels = [
                    w
                    for w in body
                    if top < (w[1] + w[3]) / 2 < bottom and w[0] <= symbol_right
                ]
                label_rows = lines(labels)
                symbol_word = next(
                    (
                        w
                        for w in labels
                        if abs(w[0] - anchor) < 8
                        and re.fullmatch(
                            r"[A-Za-z∆?][A-Za-z0-9_()/?-]{0,15}", w[4].strip(",:")
                        )
                    ),
                    None,
                )
                if symbol_word:
                    label_line = next(
                        (r for _, r in label_rows if symbol_word in r), []
                    )
                    code = row_code(
                        label_line, supported, boundaries[0], symbol_right, symbol_left
                    )
                    description = joined(labels)
                    active_y = y
            if not code or y - active_y > 130:
                continue
            unit_items = [
                w
                for w in row
                if w[0] >= boundaries[-1] and abs((w[0] + w[2]) / 2 - ux) < 35
            ]
            # An unmapped prefix glyph can turn µA into A. Never normalize that
            # ambiguous digital unit; the OCR path reads the rendered glyph.
            if any(
                r[0] >= min((w[0] for w in unit_items), default=ux) - 9
                and r[0] < ux + 20
                and abs((r[1] + r[3]) / 2 - y) < 10
                for r in missing
            ):
                continue
            unit = canonical_unit(joined(unit_items).strip())
            if unit not in DEFINITIONS[code]["units"]:
                # A unit may be vertically centered across several test rows.
                nearby = [
                    w
                    for w in body
                    if abs((w[1] + w[3]) / 2 - y) < 9
                    and w[0] >= boundaries[-1]
                    and abs((w[0] + w[2]) / 2 - ux) < 35
                ]
                matches = {
                    canonical_unit(w[4])
                    for w in nearby
                    if canonical_unit(w[4]) in DEFINITIONS[code]["units"]
                }
                unit = matches.pop() if len(matches) == 1 else previous_unit
            if unit not in DEFINITIONS[code]["units"]:
                continue
            previous_unit = unit
            conditions = "; ".join(
                s
                for s in [
                    section,
                    description,
                    joined(leading) if joined(leading) != description else "",
                ]
                if s
            )
            for i, (_, _, kind) in enumerate(columns):
                cell = joined(
                    [
                        w
                        for w in row
                        if boundaries[i] <= (w[0] + w[2]) / 2 < boundaries[i + 1]
                    ]
                )
                if not re.fullmatch(NUM, cell):
                    continue
                try:
                    out.append(
                        make_parameter(
                            code,
                            cell,
                            unit,
                            page_number,
                            f"{description}; {kind} = {cell} {unit}",
                            conditions,
                            kind,
                        )
                    )
                except ValueError:
                    pass
    return out


def catalog_parameters(page, page_number, category, make_parameter):
    """Use real catalog cells but read each physical part row inside merged cells."""
    if category not in {
        "power",
        "capacitor",
        "inductor",
        "diode",
        "connector",
        "ic",
        "other",
    }:
        return {}
    if not re.search(
        r"order\s*code|part\s+(?:number|name|no\.)|model\s+number|order\s+information|CAT\.?\s*NO\.?",
        page.get_text(),
        re.I,
    ):
        return {}
    try:
        tables = page.find_tables().tables
    except (RuntimeError, ValueError):
        return {}
    ws = words(page)
    output = {}
    # Some exporters split one ruled table into a header table and a body table.
    # Join only adjacent grids with identical physical column counts and width.
    from types import SimpleNamespace

    merged = []
    index = 0
    while index < len(tables):
        table = tables[index]
        raw = table.extract()
        physical = list(table.rows)
        has_header = any(
            re.search(
                r"part\s+(?:number|no\.)|order\s+(?:code|information)|model\s+number",
                v or "",
                re.I,
            )
            for row in raw
            for v in row
        )
        while has_header and index + 1 < len(tables):
            nxt = tables[index + 1]
            if (
                nxt.col_count != table.col_count
                or abs(nxt.bbox[0] - table.bbox[0]) > 3
                or abs(nxt.bbox[2] - table.bbox[2]) > 3
                or not -3 <= nxt.bbox[1] - physical[-1].bbox[3] <= 25
            ):
                break
            raw += nxt.extract()
            physical += list(nxt.rows)
            index += 1
        merged.append(SimpleNamespace(rows=physical, extract=lambda data=raw: data))
        index += 1
    for table in merged:
        raw_rows = table.extract()
        rows = []
        for ri, raw in enumerate(raw_rows):
            cleaned = []
            for ci, v in enumerate(raw):
                rect = table.rows[ri].cells[ci]
                text = (
                    joined(
                        [
                            w
                            for w in ws
                            if rect[0] <= (w[0] + w[2]) / 2 < rect[2]
                            and rect[1] <= (w[1] + w[3]) / 2 < rect[3]
                        ]
                    )
                    if rect
                    else ""
                )
                text = re.sub(r"\bPPaarrtt\b", "Part", text)
                text = re.sub(r"\bnnumber\b", "number", text)
                cleaned.append(text)
            rows.append(cleaned)
        hi = next(
            (
                i
                for i, row in enumerate(rows[:6])
                if any(
                    len(v or "") < 100
                    and re.search(
                        r"order\s*code|part\s+(?:number|name|no\.)|model\s+number|order\s+information|CAT\.?\s*NO\.?",
                        v or "",
                        re.I,
                    )
                    for v in row
                )
            ),
            None,
        )
        if hi is None:
            continue
        header = rows[hi]
        model_columns = [
            i
            for i, v in enumerate(header)
            if len(v) < 100
            and re.search(
                r"order\s*code|part\s+(?:number|name|no\.)|model\s+number|order\s+information|CAT\.?\s*NO\.?",
                v,
                re.I,
            )
        ]
        modelcol = max(
            model_columns,
            key=lambda c: sum(
                bool(re.search(r"[A-Za-z].*\d|\d.*[A-Za-z]", row[c]))
                for row in rows[hi + 1 : hi + 12]
            ),
        )
        specs = []
        column_kinds = {}
        data_start = next(
            (
                ri
                for ri in range(hi + 1, len(rows))
                if len(rows[ri][modelcol]) < 80
                and re.search(r"[A-Za-z].*\d|\d.*[A-Za-z]", rows[ri][modelcol])
            ),
            hi + 1,
        )
        for i, v in enumerate(header):
            label = (v or "").replace("\n", " ")
            label = re.sub(r"\s+", " ", label).strip()
            label = re.sub(r"^Nominal ", "", label, flags=re.I)
            # Units often live in a separate header row underneath a label.
            rect = table.rows[hi].cells[i]
            unit_rect = table.rows[hi + 1].cells[i] if hi + 1 < len(rows) else None
            if not rect and unit_rect:
                cx = (unit_rect[0] + unit_rect[2]) / 2
                rect = next(
                    (r for r in table.rows[hi].cells if r and r[0] <= cx < r[2]), None
                )
            if rect:
                extra = joined(
                    [
                        w
                        for w in ws
                        if rect[0] <= (w[0] + w[2]) / 2 < rect[2]
                        and rect[1] <= (w[1] + w[3]) / 2 < rect[3]
                    ]
                )
                if extra:
                    label = extra
            label = re.sub(r"^Nominal ", "", label, flags=re.I)
            label = (
                label.replace("μ", "µ")
                .replace("Ω", "Ω")
                .replace("\uf057", "Ω")
                .replace("max", " max")
                .replace("mArms", "mA")
            )
            code = next((c for pat, c in NAMES if re.search(pat, label, re.I)), None)
            header_unit = (
                canonical_unit(rows[hi + 1][i].strip()) if hi + 1 < len(rows) else ""
            )
            if not code and category == "diode":
                # Symbol groups in catalog headers often have subscripts on a
                # separate baseline: read the group and the physical unit column.
                if re.search(r"\b(?:VCL|CL)\b", label):
                    code = (
                        "VCL"
                        if header_unit == "V"
                        else "IPP" if header_unit == "A" else None
                    )
                elif re.search(r"\b(?:VBR|BR)\b", label) and header_unit == "V":
                    code = "VBR"
                elif re.search(r"\b(?:VRM|IRM|RM)\b", label):
                    code = (
                        "VR"
                        if header_unit == "V"
                        else "IR" if header_unit in {"µA", "mA", "A"} else None
                    )
                elif re.match(r"C\s*\(", label) and header_unit in {"pF", "nF", "F"}:
                    code = "CJ"
                if code and unit_rect:
                    cx = (unit_rect[0] + unit_rect[2]) / 2
                    explicit = [
                        w[4].lower().strip(".")
                        for w in ws
                        if abs((w[0] + w[2]) / 2 - cx)
                        < (unit_rect[2] - unit_rect[0]) / 2
                        and rect[1] < (w[1] + w[3]) / 2 < unit_rect[1]
                        and w[4].lower().strip(".") in {"min", "max", "typ", "nom"}
                    ]
                    if explicit:
                        column_kinds[i] = (
                            "unspecified" if explicit[-1] == "nom" else explicit[-1]
                        )
            if not code or code not in category_codes(category):
                continue
            unit = next(
                (
                    u
                    for u in sorted(DEFINITIONS[code]["units"], key=len, reverse=True)
                    if re.search(
                        r"(?<![A-Za-zµΩ])" + re.escape(u) + r"(?![A-Za-zµΩ])", label
                    )
                ),
                None,
            )
            if code == "PINS":
                unit = "1"
            if header_unit in DEFINITIONS[code]["units"]:
                unit = header_unit
            if (
                not unit
                and hi + 1 < len(rows)
                and re.fullmatch(r"V|mA|A|%|µF|pF|mΩ|W", rows[hi + 1][i].strip())
            ):
                unit = canonical_unit(rows[hi + 1][i].strip())
            notes = "; ".join(
                rows[j][i]
                for j in range(hi + 1, data_start)
                if rows[j][i]
                and canonical_unit(rows[j][i]) not in DEFINITIONS[code]["units"]
            )
            if notes:
                label += "; " + notes
            specs.append((i, code, unit, label))
        for ri in range(hi + 1, len(rows)):
            mr = table.rows[ri].cells[modelcol]
            if not mr:
                continue
            model = joined(
                [
                    w
                    for w in ws
                    if mr[0] <= (w[0] + w[2]) / 2 < mr[2]
                    and mr[1] <= (w[1] + w[3]) / 2 < mr[3]
                ]
            ).strip()
            model = re.sub(r"※2$", "", model)
            if (
                len(model) > 80
                or not re.search(r"[A-Za-z]", model)
                or not re.search(r"\d", model)
            ):
                continue
            own = [r for r in table.rows[ri].cells if r]
            top = max(r[1] for r in own)
            bottom = min(r[3] for r in own)
            for ci, code, unit, label in specs:
                rect = table.rows[ri].cells[ci]
                if not rect:
                    rect = next(
                        (
                            r.cells[ci]
                            for r in table.rows[:ri]
                            if r.cells[ci] and r.cells[ci][1] <= top < r.cells[ci][3]
                        ),
                        None,
                    )
                if not rect:
                    continue
                value = joined(
                    [
                        w
                        for w in ws
                        if rect[0] <= (w[0] + w[2]) / 2 < rect[2]
                        and top <= (w[1] + w[3]) / 2 < bottom
                    ]
                )
                # A merged input range applies to all its rows. Other merged
                # columns contain separate values: never copy the entire cell.
                if not value and code == "VIN":
                    value = joined(
                        [
                            w
                            for w in ws
                            if rect[0] <= (w[0] + w[2]) / 2 < rect[2]
                            and rect[1] <= (w[1] + w[3]) / 2 < rect[3]
                        ]
                    )
                if unit:
                    match = re.fullmatch(r"(" + NUM + r")(?:±" + NUM + r"%)?", value)
                    parsed = (
                        [
                            (
                                match.group(1),
                                unit,
                                column_kinds.get(
                                    ci,
                                    (
                                        "max"
                                        if "max" in label.lower()
                                        else (
                                            "typ"
                                            if "typ" in label.lower()
                                            else "unspecified"
                                        )
                                    ),
                                ),
                            )
                        ]
                        if match
                        else []
                    )
                else:
                    value = value.replace("VDC", "V").replace("mArms", "mA")
                    value = re.sub(r"(?<=\d)[‘’'](?=\d{3}\b)", "", value)
                    range_match = re.match(
                        r"^(" + NUM + r")\s*[–−-]\s*(" + NUM + r")\s*(V|A)", value
                    )
                    if range_match:
                        parsed = [
                            (range_match[1], range_match[3], "min"),
                            (range_match[2], range_match[3], "max"),
                        ]
                    else:
                        match = re.fullmatch(
                            r"(±)?(" + NUM + r")\s*(V|mA|A|%|W)(?:\s*±" + NUM + r"%)?",
                            value,
                        )
                        parsed = (
                            [
                                (
                                    match[2],
                                    match[3],
                                    (
                                        "typ"
                                        if "typ" in label.lower()
                                        else (
                                            "max"
                                            if "max" in label.lower()
                                            else "unspecified"
                                        )
                                    ),
                                )
                            ]
                            if match
                            else []
                        )
                for number, u, kind in parsed:
                    try:
                        p = make_parameter(
                            code,
                            number,
                            u,
                            page_number,
                            f"{model}: {label} = {value}",
                            label
                            + (
                                "; ±: значение для каждого плеча"
                                if value.startswith("±")
                                else ""
                            ),
                            kind,
                        )
                        names = (
                            model.split()
                            if len(model.split()) > 1
                            and all(
                                re.fullmatch(r"[A-Z0-9-]+", m)
                                and re.search(r"[A-Z]", m)
                                and re.search(r"\d", m)
                                for m in model.split()
                            )
                            else [model]
                        )
                        for name in names:
                            output.setdefault(name, []).append(p.copy())
                    except ValueError:
                        pass
    return output


def described_parameters(page, page_number, category, make_parameter):
    """Explicit labeled specifications outside tables, including drawing pitch."""
    text = joined(words(page))
    supported = set(category_codes(category))
    out = []
    rules = [
        ("PITCH", r"\((" + NUM + r")\s*mm\)[^ ]{0,20}\s*micropitch", "mm"),
        ("PITCH", r"\b(" + NUM + r")\s*mm\s*SPACING\b", "mm"),
        ("PITCH", r"\bPitch\s*[:=]\s*(" + NUM + r")", "mm"),
        (
            "L",
            r"\b(?:Inductance\s*[:=]?|Pin\s*\d+\s*-\s*\d+\s*:)\s*("
            + NUM
            + r")\s*(µH|μH|uH|mH|H)",
            None,
        ),
        ("DCR", r"\bDCR\s*\(Max\)\s*:\s*(" + NUM + r")\s*(mΩ|mΩ|mohm|Ω|Ω|ohm)", None),
        ("IRATED", r"\bIdc\s*\(Max\)\s*:\s*(" + NUM + r")\s*(mA|A)", None),
        ("IRATED", r"\bCurrent\s*Rating\s*:\s*(" + NUM + r")\s*(mA|A)", None),
        (
            "CONTACT_R",
            r"\bContact\s*Resistance\s*:\s*(" + NUM + r")\s*(mohm|ohm|mΩ|Ω)(?:\s*max)?",
            None,
        ),
        ("Z", r"\b(?:impedance|socket)\s*[:=]?\s*(" + NUM + r")\s*(OHMS|ohms|Ω)", None),
    ]
    for code, pattern, unit in rules:
        if code not in supported:
            continue
        for match in re.finditer(pattern, text, re.I):
            try:
                u = unit or match[2]
                u = {"OHMS": "ohm", "uH": "µH"}.get(u, u)
                item = make_parameter(
                    code,
                    match[1],
                    u,
                    page_number,
                    match.group(),
                    match.group(),
                    "max" if re.search(r"max", match.group(), re.I) else "unspecified",
                )
                if not any(
                    p["code"] == item["code"] and p["value"] == item["value"]
                    for p in out
                ):
                    out.append(item)
            except ValueError:
                pass
    return out


def aligned_catalog_parameters(page, page_number, category, make_parameter):
    """Catalogs without grids: explicit part column plus labeled value columns."""
    ws = words(page)
    result = {}
    queries = ["Order Information", "Part number", "Part No.", "Order code"]
    anchors = [r for q in queries for r in page.search_for(q)]
    if not anchors:
        return result
    supported = set(category_codes(category))
    captions = [
        ("VOUT", "Output Voltage", "V"),
        ("VIN", "Input Voltage", "V"),
        ("VRATED", "Rated voltage", "V"),
        ("IRATED", "Rated current", "A"),
        ("C", "Rated capacitance", "µF"),
        ("VF", "VF (V)", "V"),
    ]
    for anchor in anchors:
        ax = (anchor.x0 + anchor.x1) / 2
        ay = (anchor.y0 + anchor.y1) / 2
        models = [
            w
            for w in ws
            if (w[1] + w[3]) / 2 > ay + 6
            and abs((w[0] + w[2]) / 2 - ax) < 70
            and re.fullmatch(
                r"(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9][A-Za-z0-9./_-]{4,60}", w[4]
            )
        ]
        if not models:
            continue
        first = min((w[1] + w[3]) / 2 for w in models)
        columns = []
        for code, query, unit in captions:
            if code not in supported:
                continue
            boxes = [
                r for r in page.search_for(query) if abs((r.y0 + r.y1) / 2 - ay) < 45
            ]
            if not boxes:
                continue
            # Subscripted symbols can return several rectangles for one caption.
            box = boxes[0]
            for r in boxes[1:]:
                if abs(r.y0 - box.y0) < 8 and r.x0 - box.x1 < 20:
                    box = box | r
            cx = (box.x0 + box.x1) / 2
            nearby = [
                w
                for w in ws
                if abs((w[0] + w[2]) / 2 - cx) < max(35, box.width / 2 + 12)
                and box.y0 - 6 < (w[1] + w[3]) / 2 < first - 3
            ]
            # Require the printed unit, not a guessed unit inferred from a code.
            label = joined(nearby).replace("μ", "µ")
            if not re.search(
                r"(?<![A-Za-zµ])" + re.escape(unit) + r"(?![A-Za-zµ])", label
            ):
                continue
            kinds = [
                w for w in nearby if w[4].lower().strip(".") in {"min", "typ", "max"}
            ]
            if kinds:
                for w in kinds:
                    columns.append(
                        (
                            code,
                            (w[0] + w[2]) / 2,
                            unit,
                            w[4].lower().strip("."),
                            label,
                            12,
                        )
                    )
            else:
                columns.append(
                    (code, cx, unit, "unspecified", label, max(18, box.width / 2))
                )
        for m in models:
            y = (m[1] + m[3]) / 2
            for code, cx, unit, kind, label, width in columns:
                values = [
                    w
                    for w in ws
                    if abs((w[1] + w[3]) / 2 - y) < 3
                    and abs((w[0] + w[2]) / 2 - cx) < width
                ]
                if len(values) != 1:
                    continue
                value = values[0][4]
                number = value.strip("()")
                if not re.fullmatch(NUM, number):
                    continue
                condition = label + (
                    "; значение в скобках: отдельные условия в заголовке PDF"
                    if value.startswith("(")
                    else ""
                )
                try:
                    p = make_parameter(
                        code,
                        number,
                        unit,
                        page_number,
                        f"{m[4]}: {label} = {value} {unit}",
                        condition,
                        kind,
                    )
                    result.setdefault(m[4], []).append(p)
                except ValueError:
                    pass
    return result


def specification_parameters(page, page_number, category, make_parameter):
    """Two-column PARAMETER/SPECIFICATION tables with units inside value cells."""
    text = page.get_text()
    if not re.search(r"PARAMETER\s+SPECIFICATIONS?", text, re.I):
        return []
    try:
        tables = page.find_tables().tables
    except (RuntimeError, ValueError):
        return []
    out = []
    ws = words(page)
    supported = set(category_codes(category))
    for table in tables:
        rows = table.extract()
        hi = next(
            (
                i
                for i, row in enumerate(rows[:4])
                if any(re.search(r"SPECIFICATIONS?", v or "", re.I) for v in row)
            ),
            None,
        )
        if hi is None:
            continue
        for ri in range(hi + 1, len(rows)):
            rect = table.rows[ri].cells[0]
            if not rect:
                continue
            description = joined(
                [
                    w
                    for w in ws
                    if rect[0] <= (w[0] + w[2]) / 2 < rect[2]
                    and rect[1] <= (w[1] + w[3]) / 2 < rect[3]
                ]
            )
            label = re.sub(r"\s+", "", description).upper()
            code = (
                "L"
                if label.startswith("INDUCTANCE")
                else (
                    "DCR"
                    if label.startswith("DCRESISTANCE") and "IMBALANCE" not in label
                    else (
                        "TURN_RATIO"
                        if label.startswith("TURNSRATIO")
                        else (
                            "VISOL"
                            if label.startswith("INPUT-OUTPUTISOLATION")
                            or label.startswith("ISOLATIONVOLTAGE")
                            else ""
                        )
                    )
                )
            )
            if code not in supported:
                continue
            for vr in table.rows[ri].cells[1:]:
                if not vr:
                    continue
                value = joined(
                    [
                        w
                        for w in ws
                        if vr[0] <= (w[0] + w[2]) / 2 < vr[2]
                        and vr[1] <= (w[1] + w[3]) / 2 < vr[3]
                    ]
                )
                if code == "TURN_RATIO":
                    match = re.fullmatch("(" + NUM + r")(?:±" + NUM + r"%)?", value)
                    unit = "1"
                else:
                    units = sorted(
                        set(DEFINITIONS[code]["units"])
                        | {"uH", "OHMS", "ohms", "VRMS", "VDC"},
                        key=len,
                        reverse=True,
                    )
                    match = re.search(
                        r"(?<![\w.])("
                        + NUM
                        + r")\s*("
                        + "|".join(re.escape(u) for u in units)
                        + r")(?=MIN|MAX|[^A-Za-z]|$)",
                        value,
                    )
                    unit = match[2] if match else ""
                    unit = {
                        "uH": "µH",
                        "OHMS": "Ω",
                        "ohms": "Ω",
                        "VRMS": "V",
                        "VDC": "V",
                    }.get(unit, unit)
                if not match:
                    continue
                kind = (
                    "min"
                    if re.search(r"MIN(?:\b|@)", value, re.I)
                    else (
                        "max"
                        if re.search(r"MAX(?:\b|@)", value, re.I)
                        else "unspecified"
                    )
                )
                try:
                    out.append(
                        make_parameter(
                            code,
                            match[1],
                            unit,
                            page_number,
                            description + " = " + value,
                            description + "; " + value,
                            kind,
                        )
                    )
                except ValueError:
                    pass
    return out


def drawing_positions(page, page_number, model, make_parameter):
    """A drawing may abbreviate part numbers to suffixes in a POS table."""
    part = re.fullmatch(r"([A-Za-z0-9]+)-(\d+)", model)
    if not part or not re.search(r"\b" + re.escape(part[1]) + r"\b", page.get_text()):
        return []
    ws = words(page)
    out = []
    for pos in [w for w in ws if w[4] == "POS"]:
        py = (pos[1] + pos[3]) / 2
        px = (pos[0] + pos[2]) / 2
        labels = [
            w
            for w in ws
            if w[4] in {"P/N", "PART", "NUMBER"}
            and abs((w[1] + w[3]) / 2 - py) < 18
            and 15 < px - (w[0] + w[2]) / 2 < 100
        ]
        if not labels:
            continue
        mx = sum((w[0] + w[2]) / 2 for w in labels) / len(labels)
        for suffix in ws:
            if (
                suffix[4] != "-" + part[2]
                or abs((suffix[0] + suffix[2]) / 2 - mx) > 35
                or not 0 < py - (suffix[1] + suffix[3]) / 2 < 160
            ):
                continue
            values = [
                w
                for w in ws
                if re.fullmatch(r"\d+", w[4])
                and abs((w[1] + w[3] - suffix[1] - suffix[3]) / 2) < 3
                and abs((w[0] + w[2]) / 2 - px) < 12
            ]
            if len(values) == 1:
                p = make_parameter(
                    "PINS",
                    values[0][4],
                    "1",
                    page_number,
                    f"{model}: POS = {values[0][4]} (строка суффикса -{part[2]} таблицы PART NUMBER/POS)",
                    kind="unspecified",
                )
                if not any(v["value"] == p["value"] for v in out):
                    out.append(p)
    return out
