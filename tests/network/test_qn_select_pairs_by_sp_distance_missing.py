import csv
import subprocess
from pathlib import Path


def test_select_pairs_by_sp_distance_missing(tmp_path: Path):
    edge_csv = tmp_path / "edges.csv"
    with edge_csv.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["u", "v", "linkLengthInKm"])
        writer.writerow(["1", "2", "10"])
        writer.writerow(["2", "3", "10"])
        writer.writerow(["1", "3", "25"])

    out_csv = tmp_path / "pairs.csv"
    subprocess.run(
        [
            "python",
            "scripts/qn_select_pairs_by_sp_distance.py",
            "--edge-distance-csv",
            str(edge_csv),
            "--topology-id",
            "toy",
            "--targets-km",
            "404,511,1002",
            "--pairs-per-target",
            "2",
            "--pair-distance-rel-tol",
            "0.01",
            "--out-csv",
            str(out_csv),
        ],
        check=True,
    )

    with out_csv.open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 6
    assert any(r["found"].lower() in ("false", "0") for r in rows)
