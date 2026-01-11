import csv
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.qn_topology_feasibility import compute_target_feasibility, filter_candidates_by_feasibility
from scripts.qn_topologies import load_edge_distances_csv


def _write_edges(path: Path, edges):
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["u", "v", "linkLengthInKm"])
        writer.writerows(edges)


def test_feasibility_selection_prefers_long_feasible():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        small_csv = base / "small.csv"
        large_csv = base / "large.csv"
        # small diameter (~20 km)
        _write_edges(small_csv, [["A", "B", 10], ["B", "C", 10], ["A", "C", 15]])
        # large diameter (~1000 km)
        _write_edges(large_csv, [["A", "B", 500], ["B", "C", 500], ["A", "C", 1000]])

        targets = [404.0, 511.0, 1002.0]
        small = compute_target_feasibility(
            load_edge_distances_csv(small_csv),
            targets,
            pairs_per_target=1,
            abs_tol=0.0,
            rel_tol=0.2,
        )
        large = compute_target_feasibility(
            load_edge_distances_csv(large_csv),
            targets,
            pairs_per_target=1,
            abs_tol=0.0,
            rel_tol=0.2,
        )

        candidates = [
            {"topology_id": "small", "missing_total": small["total_missing"], "missing_long": small["missing_long"], "completeness": small["completeness"], "diameter_km": 20.0},
            {"topology_id": "large", "missing_total": large["total_missing"], "missing_long": large["missing_long"], "completeness": large["completeness"], "diameter_km": 1000.0},
        ]
        filtered = filter_candidates_by_feasibility(candidates, require_long_feasible=True, require_target_feasible=False)
        ids = [c["topology_id"] for c in filtered]
        assert "large" in ids
        assert "small" not in ids
