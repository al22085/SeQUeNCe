import csv
import subprocess
from pathlib import Path


def test_select_pairs_by_sp_distance(tmp_path: Path):
    edge_csv = tmp_path / "edges.csv"
    with edge_csv.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["u", "v", "linkLengthInKm"])
        writer.writerow(["1", "2", "100"])
        writer.writerow(["2", "3", "100"])
        writer.writerow(["3", "4", "100"])
        writer.writerow(["1", "4", "500"])
        writer.writerow(["1", "3", "250"])
        writer.writerow(["2", "4", "250"])

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
            "100,200,300",
            "--pairs-per-target",
            "2",
            "--pair-distance-rel-tol",
            "0.5",
            "--out-csv",
            str(out_csv),
        ],
        check=True,
    )

    with out_csv.open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 6
    assert rows[0]["topology_id"] == "toy"
    labels = [r["label"] for r in rows]
    assert labels[:2] == ["short_1", "short_2"]
    assert labels[2:4] == ["medium_1", "medium_2"]
    assert labels[4:6] == ["long_1", "long_2"]
    pairs = {(r["src_node"], r["dst_node"]) for r in rows}
    assert len(pairs) >= 4
    assert "dist_km" in rows[0]
    assert "rel_error" in rows[0]
