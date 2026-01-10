import hashlib
import tempfile
import zipfile
from pathlib import Path

import subprocess


def _md5(path: Path) -> str:
    h = hashlib.md5()
    h.update(path.read_bytes())
    return h.hexdigest()


def test_topologybench_fetch_with_local_zip():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        real_zip = Path(__file__).resolve().parents[2] / "data" / "topologybench" / "real_topologies.zip"
        real_md5 = _md5(real_zip) if real_zip.exists() else None
        zip_path = base / "real_topologies.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("TOP_75_TOY1.xlsx", "dummy")

        manifest = base / "manifest.json"
        manifest.write_text(
            "{"
            f"\"record_id\": 1,"
            f"\"filename\": \"real_topologies.zip\","
            f"\"md5\": \"{_md5(zip_path)}\","
            "\"source\": \"test\","
            "\"retrieved_via\": \"file://\""
            "}"
        )

        cmd = [
            "python",
            "scripts/qn_topologybench_fetch.py",
            "--topologybench-zip",
            str(zip_path),
            "--manifest",
            str(manifest),
            "--no-download",
            "--no-copy",
        ]
        subprocess.run(cmd, check=True, cwd=Path(__file__).resolve().parents[2])
        if real_md5:
            assert _md5(real_zip) == real_md5
