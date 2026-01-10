import hashlib
import json
import subprocess
import tempfile
import zipfile
from pathlib import Path


def _write_minimal_xlsx(path: Path):
    shared = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<si><t>source</t></si><si><t>destination</t></si><si><t>linkLengthInKm</t></si>"
        "<si><t>A</t></si><si><t>B</t></si></sst>"
    )
    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<sheetData><row>"
        "<c t=\"s\"><v>0</v></c><c t=\"s\"><v>1</v></c><c t=\"s\"><v>2</v></c>"
        "</row><row>"
        "<c t=\"s\"><v>3</v></c><c t=\"s\"><v>4</v></c><c><v>10</v></c>"
        "</row></sheetData></worksheet>"
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


def test_auto_select_insufficient_topologies_errors():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        real_zip = Path(__file__).resolve().parents[2] / "data" / "topologybench" / "real_topologies.zip"
        real_md5 = None
        if real_zip.exists():
            real_md5 = _md5(real_zip)
        xlsx = base / "TOP_75_ONLYONE.xlsx"
        _write_minimal_xlsx(xlsx)
        zip_path = base / "real_topologies.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.write(xlsx, arcname=xlsx.name)

        manifest = {
            "record_id": 0,
            "filename": "real_topologies.zip",
            "md5": "d41d8cd98f00b204e9800998ecf8427e",
            "source": "test fixture",
            "retrieved_via": "local",
        }
        # update md5 for the created zip
        import hashlib
        h = hashlib.md5()
        with zip_path.open("rb") as f:
            h.update(f.read())
        manifest["md5"] = h.hexdigest()
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
            "--no-copy",
            "--no-verify-parallel",
            "--auto-select-topologies",
            "3",
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
        proc = subprocess.run(cmd, cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True)
        assert proc.returncode != 0
        assert "TopologyBench zip appears to contain only" in proc.stderr
        if real_md5:
            assert _md5(real_zip) == real_md5
