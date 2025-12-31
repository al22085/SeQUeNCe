import csv
import tempfile
import zipfile
from pathlib import Path

import subprocess


def _write_minimal_xlsx(path: Path, rows):
    strings = []
    for row in rows:
        for val in row:
            if isinstance(val, str) and val not in strings:
                strings.append(val)
    sst_items = "".join([f"<si><t>{s}</t></si>" for s in strings])
    shared = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"{sst_items}</sst>"
    )

    def cell(val):
        if isinstance(val, str):
            return f'<c t="s"><v>{strings.index(val)}</v></c>'
        return f"<c><v>{val}</v></c>"

    rows_xml = []
    for row in rows:
        cells = "".join([cell(v) for v in row])
        rows_xml.append(f"<row>{cells}</row>")
    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(rows_xml)}</sheetData></worksheet>"
    )

    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("xl/sharedStrings.xml", shared)
        zf.writestr("xl/worksheets/sheet1.xml", sheet)


def test_topologybench_generic_import_list_select():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        xlsx1 = base / "TOP_75_TOY1.xlsx"
        xlsx2 = base / "TOP_75_TOY2.xlsx"
        rows = [
            ["source", "destination", "linkLengthInKm"],
            ["A", "B", 10],
            ["B", "C", 15],
        ]
        _write_minimal_xlsx(xlsx1, rows)
        _write_minimal_xlsx(xlsx2, rows)

        out_dir = base / "out"
        out_dir.mkdir(parents=True, exist_ok=True)

        # import both
        subprocess.run(
            [
                "python",
                "scripts/qn_import_distances_from_topologybench_generic.py",
                "--xlsx",
                str(xlsx1),
                "--topology-id",
                "TOY1",
                "--out-dir",
                str(out_dir),
            ],
            check=True,
            cwd=Path(__file__).resolve().parents[2],
        )
        csv_path = out_dir / "TOY1_distances.csv"
        assert csv_path.exists()

        # list
        list_csv = out_dir / "list.csv"
        subprocess.run(
            [
                "python",
                "scripts/qn_list_topologybench.py",
                "--xlsx-dir",
                str(base),
                "--out-csv",
                str(list_csv),
            ],
            check=True,
            cwd=Path(__file__).resolve().parents[2],
        )
        assert list_csv.exists()
        with list_csv.open() as f:
            rows = list(csv.DictReader(f))
        assert len(rows) >= 2

        # select
        sel_csv = out_dir / "selected.csv"
        subprocess.run(
            [
                "python",
                "scripts/qn_select_diverse_topologies.py",
                "--list-csv",
                str(list_csv),
                "--k",
                "2",
                "--min-nodes",
                "2",
                "--max-nodes",
                "5",
                "--out-csv",
                str(sel_csv),
            ],
            check=True,
            cwd=Path(__file__).resolve().parents[2],
        )
        assert sel_csv.exists()
