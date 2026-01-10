import csv
import hashlib
import json
import subprocess
import tempfile
import zipfile
from pathlib import Path


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


def _md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def test_auto_select_with_fake_zip_smoke():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        xlsx_dir = base / "xlsx"
        xlsx_dir.mkdir(parents=True, exist_ok=True)
        rows = [
            ["source", "destination", "linkLengthInKm"],
            ["A", "B", 10],
            ["B", "C", 12],
            ["A", "C", 15],
        ]
        topo_ids = ["TOY1", "TOY2", "TOY3"]
        for tid in topo_ids:
            _write_minimal_xlsx(xlsx_dir / f"TOP_75_{tid}.xlsx", rows)

        zip_path = base / "real_topologies.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            for tid in topo_ids:
                src = xlsx_dir / f"TOP_75_{tid}.xlsx"
                zf.write(src, arcname=src.name)

        manifest = {
            "record_id": 0,
            "filename": "real_topologies.zip",
            "md5": _md5(zip_path),
            "source": "test fixture",
            "retrieved_via": "local",
        }
        manifest_path = base / "manifest.json"
        manifest_path.write_text(json.dumps(manifest))

        out_dir = base / "out"
        cmd = [
            "python",
            "scripts/qn_run_topology_policy_upgrade_curves.py",
            "--topologybench-zip",
            str(zip_path),
            "--manifest",
            str(manifest_path),
            "--no-download",
            "--auto-select-topologies",
            "3",
            "--min-nodes",
            "2",
            "--max-nodes",
            "5",
            "--upgrade-policies",
            "global_rank",
            "--upgrade-k-list",
            "0,1",
            "--eta",
            "0.9",
            "--target",
            "0.99",
            "--kbits",
            "1.0",
            "--seeds",
            "0",
            "--load-min",
            "0.01",
            "--load-max",
            "0.05",
            "--load-tol",
            "0.02",
            "--horizon-s",
            "0.05",
            "--tau-s",
            "0.02",
            "--attempt-rate-opt-hz",
            "5000",
            "--attempt-rate-sc-hz",
            "10000",
            "--coherence-opt-s",
            "0.05",
            "--coherence-sc-s",
            "0.1",
            "--loss-db-per-km",
            "0.2",
            "--segment-length-km",
            "50",
            "--workers",
            "2",
            "--out-dir",
            str(out_dir),
        ]
        subprocess.run(cmd, check=True, cwd=Path(__file__).resolve().parents[2])
        summary = out_dir / "summary_upgrade_curves.csv"
        assert summary.exists()
        selection = out_dir / "topology_selection.json"
        assert selection.exists()
