import csv
import json
import subprocess
import tempfile
from pathlib import Path


def test_sweep_pair_tolerance_smoke():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        edge_csv = base / "toy.csv"
        edge_csv.write_text(
            "u,v,linkLengthInKm\nA,B,10\nB,C,10\nC,D,10\n",
        )
        out_dir = base / "tol_sweep"
        cmd = [
            "python",
            "scripts/qn_sweep_pair_tolerance.py",
            "--root-out-dir",
            str(out_dir),
            "--edge-csv-list",
            str(edge_csv),
            "--topology-id-list",
            "toy",
            "--targets-km",
            "10,20,33",
            "--pairs-per-target",
            "1",
            "--tolerances",
            "0.05,0.1",
            "--require-long-feasible",
        ]
        subprocess.run(cmd, check=True, cwd=Path(__file__).resolve().parents[2])

        summary = out_dir / "tolerance_missing_summary.csv"
        chosen = out_dir / "chosen_tolerance.json"
        assert summary.exists()
        assert chosen.exists()
        data = json.loads(chosen.read_text())
        assert data["chosen_tolerance"] == 0.1
        rows = list(csv.DictReader(summary.open()))
        selected = [
            r
            for r in rows
            if r["tolerance"] == "0.1" and r["topology_id"] == "SELECTED_SET" and r["label"] == "all"
        ]
        assert selected
        assert selected[0]["missing_long"] == "0"
