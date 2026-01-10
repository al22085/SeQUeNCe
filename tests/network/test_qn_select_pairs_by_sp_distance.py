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
            "--out-csv",
            str(out_csv),
        ],
        check=True,
    )

    with out_csv.open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 3
    labels = [r["label"] for r in rows]
    assert labels == ["short", "medium", "long"]
    assert (rows[0]["src_node"], rows[0]["dst_node"], rows[0]["sp_km"]) == ("1", "2", "100.0")
    assert (rows[1]["src_node"], rows[1]["dst_node"], rows[1]["sp_km"]) == ("1", "3", "200.0")
    assert (rows[2]["src_node"], rows[2]["dst_node"], rows[2]["sp_km"]) == ("1", "4", "300.0")
