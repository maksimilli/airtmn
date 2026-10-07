"""Verify the user's private PDF corpus through real import/save endpoints.

Usage: PYTHONPATH=backend python backend/scripts/verify_datasheets.py PDF_DIRECTORY
The PDFs are not bundled in the repository. SHA-256 identifies renamed files.
All database and document writes are isolated in a temporary directory.
"""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import time

from fastapi.testclient import TestClient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).parents[1] / "tests/data1_expected.json",
    )
    parser.add_argument("--output", type=Path, default=Path("datasheet-report.json"))
    args = parser.parse_args()
    cases = json.loads(args.manifest.read_text(encoding="utf-8"))["cases"]
    files = {
        hashlib.sha256(f.read_bytes()).hexdigest(): f
        for f in args.directory.rglob("*")
        if f.is_file() and f.suffix.lower() == ".pdf"
    }
    records = []
    with tempfile.TemporaryDirectory(prefix="catalog-validation-") as directory:
        os.environ["CATALOG_DATA_DIR"] = directory
        from app.main import app

        with TestClient(app) as client:
            for case in cases:
                started = time.monotonic()
                f = files.get(case["sha256"])
                errors = []
                record = dict(
                    filename=case["filename"],
                    category=case["category"],
                    errors=errors,
                    expected=case["expected"],
                )
                if not f:
                    errors.append("Исходный PDF с указанным SHA-256 отсутствует")
                else:
                    response = client.post(
                        "/api/import",
                        data={"category": case["category"]},
                        files={
                            "file": (
                                case["filename"],
                                f.read_bytes(),
                                "application/pdf",
                            )
                        },
                    )
                    record["status"] = response.status_code
                    if response.status_code != 200:
                        errors.append(str(response.json()))
                    else:
                        data = response.json()
                        record.update(
                            name=data["name"],
                            manufacturer=data["manufacturer"],
                            page_count=data["page_count"],
                            parameters=data["parameters"],
                            variants_count=len(data["variants"]),
                            ocr=data["ocr"],
                            warnings=data["warnings"],
                        )
                        for expected in case["expected"]:
                            matching = [
                                p
                                for p in data["parameters"]
                                if p["code"] == expected["code"]
                                and math.isclose(
                                    p["value"],
                                    expected["value"],
                                    rel_tol=1e-8,
                                    abs_tol=1e-15,
                                )
                                and (
                                    expected["kind"] is None
                                    or p["kind"] == expected["kind"]
                                )
                            ]
                            if not matching:
                                errors.append(
                                    "Не найдена контрольная характеристика "
                                    + str(expected)
                                )
                        if not data["parameters"]:
                            errors.append("Не заполнено ни одной характеристики")
                        if not all(
                            p["page"] and p["evidence"] for p in data["parameters"]
                        ):
                            errors.append("Отсутствует ссылка на источник")
                        payload = {
                            key: data[key]
                            for key in [
                                "name",
                                "manufacturer",
                                "package",
                                "category",
                                "document_id",
                                "parameters",
                            ]
                        }
                        saved = client.post("/api/components", json=payload)
                        record["save_status"] = saved.status_code
                        if saved.status_code != 201:
                            errors.append("Ошибка сохранения: " + str(saved.json()))
                        else:
                            reread = client.get(
                                "/api/components/" + str(saved.json()["id"])
                            ).json()
                            if len(reread["parameters"]) != len(data["parameters"]):
                                errors.append("Характеристики потеряны при сохранении")
                record["seconds"] = round(time.monotonic() - started, 2)
                records.append(record)
                args.output.write_text(
                    json.dumps(records, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                print(
                    ("PASS" if not errors else "FAIL"),
                    case["filename"],
                    record.get("name", ""),
                    len(record.get("parameters", [])),
                    f"{record['seconds']}s",
                    "; ".join(errors),
                    flush=True,
                )
    failed = sum(bool(r["errors"]) for r in records)
    print(
        f'{len(records)-failed}/{len(records)} PDF; {sum(len(r["expected"]) for r in records)} контрольных значений; ошибок: {failed}'
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
