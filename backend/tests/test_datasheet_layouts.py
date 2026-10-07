"""Regression formats from real manufacturer sheets; no manufacturer PDFs bundled."""

import fitz
import pytest
from app.extraction import extract
from app.classification import detect_category


def grid_pdf(title, rows, xs, ys):
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((40, 30), title)
    for y, row in zip(ys, rows):
        for x, text in zip(xs, row):
            if text:
                page.insert_text((x, y), text, fontsize=10)
    return pdf


def test_no_symbol_header_and_incidental_resistors():
    with grid_pdf(
        "www.example.com\nAMP987 integrated circuit with external resistors",
        [
            ["PARAMETER", "TEST CONDITIONS", "MIN", "TYP", "MAX", "UNIT"],
            ["VCC Supply voltage", "", "1.65", "", "5.5", "V"],
            ["VIH High level input", "", "1.7", "", "", "V"],
            ["ICC Supply current", "", "", "5", "10", "µA"],
        ],
        [40, 240, 350, 400, 450, 500],
        [85, 115, 145, 175],
    ) as pdf:
        data = extract(pdf, category="ic", filename="Maker_AMP987.pdf")
    assert data["name"] == "AMP987"
    values = [(p["code"], p["value"], p["kind"]) for p in data["parameters"]]
    assert ("VCC", 1.65, "min") in values and ("VCC", 5.5, "max") in values
    assert not any(p["code"] == "VCC" and p["value"] == 1.7 for p in data["parameters"])
    assert ("ICC", pytest.approx(1e-5), "max") in values


@pytest.mark.parametrize(
    "title",
    [
        "SN65HVD251 CAN transceiver with external resistor",
        "Si8422 digital isolator with capacitors",
        "TPS386000 Quad Supply Voltage Supervisor with resistors",
    ],
)
def test_identity_wins_over_application_parts(title):
    assert detect_category([title])["category"] == "ic"


def test_catalog_separate_models_and_merged_cells():
    with fitz.open() as pdf:
        p = pdf.new_page()
        p.insert_text((40, 30), "DC/DC Converters")
        xs = [40, 175, 305, 410, 530]
        ys = [80, 110, 140, 170]
        for y in ys:
            p.draw_line((xs[0], y), (xs[-1], y))
        for x in xs:
            p.draw_line((x, ys[0]), (x, ys[-1]))
        for row, y in zip(
            [
                [
                    "Order code",
                    "Input voltage",
                    "Output voltage",
                    "Output current max.",
                ],
                ["MODULE 12-01", "4.5 - 9.0 VDC", "3.3 VDC", "700 mA"],
                ["MODULE 12-02", "4.5 - 9.0 VDC", "5 VDC", "600 mA"],
            ],
            [100, 130, 160],
        ):
            for x, value in zip(xs, row):
                p.insert_text((x + 4, y), value, fontsize=8)
        data = extract(pdf, category="power", filename="catalog.pdf")
    byname = {v["name"]: v["parameters"] for v in data["variants"]}
    assert set(byname) == {"MODULE 12-01", "MODULE 12-02"}
    assert (
        next(p["value"] for p in byname["MODULE 12-01"] if p["code"] == "VOUT") == 3.3
    )
    assert next(p["value"] for p in byname["MODULE 12-02"] if p["code"] == "VOUT") == 5
    assert [
        (p["value"], p["kind"]) for p in byname["MODULE 12-02"] if p["code"] == "VIN"
    ] == [(4.5, "min"), (9, "max")]


def test_unruled_catalog_with_typ_max_and_source_conditions():
    with grid_pdf(
        "SMD CHIP LED",
        [
            ["Part No.", "", "VF (V)", ""],
            ["", "", "Typ.", "Max."],
            ["LED123", "", "2.1", "2.6"],
            ["LED456", "", "1.8", "2.2"],
        ],
        [40, 220, 310, 345],
        [90, 110, 140, 160],
    ) as pdf:
        data = extract(pdf, category="diode", filename="led_catalog.pdf")
    byname = {v["name"]: v for v in data["variants"]}
    assert byname["LED123"]["parameters"][0]["code"] == "VF"
    assert {(p["value"], p["kind"]) for p in byname["LED123"]["parameters"]} == {
        (2.1, "typ"),
        (2.6, "max"),
    }
    assert {(p["value"], p["kind"]) for p in byname["LED456"]["parameters"]} == {
        (1.8, "typ"),
        (2.2, "max"),
    }


def test_drawing_has_pitch_and_does_not_invent_electrical_ratings():
    with grid_pdf("Connector CMM220", [["Pitch=2"]], [40], [90]) as pdf:
        data = extract(pdf, category="connector", filename="drawing.pdf")
    assert [(p["code"], p["value"], p["unit"]) for p in data["parameters"]] == [
        ("PITCH", 2, "mm")
    ]


def test_filename_must_not_truncate_a_real_model():
    with grid_pdf("MODEL123 integrated circuit", [["VCC = 3.3 V"]], [40], [90]) as pdf:
        data = extract(pdf, category="ic", filename="MODEL12.pdf")
    assert data["name"] == "MODEL123"


def test_description_vdd_does_not_override_explicit_uvlo_symbol():
    with grid_pdf(
        "ISO789 digital isolator",
        [
            ["PARAMETER", "SYMBOL", "MIN", "TYP", "MAX", "UNIT"],
            ["VDD Undervoltage Threshold", "VDDUV+", "2.15", "2.3", "2.5", "V"],
            ["VDD Hysteresis", "VDDHYS", "45", "75", "95", "mV"],
        ],
        [40, 250, 350, 400, 450, 500],
        [85, 115, 145],
    ) as pdf:
        data = extract(pdf, category="ic", filename="ISO789.pdf")
    assert not any(p["code"] == "VCC" for p in data["parameters"])
    assert any(
        p["code"] == "UVLO" and p["value"] == 2.3 and p["kind"] == "typ"
        for p in data["parameters"]
    )
    assert any(
        p["code"] == "VHYST" and p["value"] == pytest.approx(0.075)
        for p in data["parameters"]
    )


def test_decimal_without_leading_zero_in_connector_specification():
    with grid_pdf(
        "Connector SOCKET789",
        [["Current Rating: .75 A", ""], ["Contact Resistance: 15 mohm max", ""]],
        [40, 300],
        [90, 120],
    ) as pdf:
        data = extract(pdf, category="connector", filename="SOCKET789.pdf")
    assert any(p["code"] == "IRATED" and p["value"] == 0.75 for p in data["parameters"])
    assert any(
        p["code"] == "CONTACT_R" and p["value"] == 0.015 and p["kind"] == "max"
        for p in data["parameters"]
    )
