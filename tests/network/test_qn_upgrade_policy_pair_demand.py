import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.qn_topologies import subdivide_edges, edge_usage_counts_for_pairs
from scripts.qn_analyze_upgrade_threshold import compute_path_coverage


def test_pair_demand_coverage_monotone():
    # Simple triangle graph: A-B-C shorter than A-C direct.
    dist_map = {
        ("A", "B"): 100_000.0,
        ("B", "C"): 100_000.0,
        ("A", "C"): 300_000.0,
    }
    expanded_edges, _, _ = subdivide_edges(dist_map, segment_length_km=50.0)
    pairs = [("A", "C")]
    counts = edge_usage_counts_for_pairs(expanded_edges, pairs)
    ranked = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
    upgrade_sets = []
    for k in [0, 1, 2]:
        upgrade_sets.append(set([e for e, _ in ranked[:k]]))

    prev_upgraded = -1
    prev_frac = -1.0
    for upgraded in upgrade_sets:
        cov = compute_path_coverage(expanded_edges, "A", "C", upgraded)
        assert cov["path_edges_upgraded"] >= prev_upgraded
        assert cov["path_upgraded_fraction"] >= prev_frac
        prev_upgraded = cov["path_edges_upgraded"]
        prev_frac = cov["path_upgraded_fraction"]
