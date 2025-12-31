import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.qn_analyze_upgrade_threshold import compute_path_coverage
from scripts.qn_topologies import (
    load_distance_dataset,
    subdivide_edges,
    nsfnet_topology,
    pick_upgrade_edges,
)


def test_upgrade_path_coverage_monotone():
    dist_map = load_distance_dataset("topologybench_nsfnet13")
    expanded_edges, _, _ = subdivide_edges(dist_map, segment_length_km=50.0)
    topo = nsfnet_topology()
    ks = [0, 3, 7, 21]
    prev_upgraded = -1
    prev_frac = -1.0
    for k in ks:
        upgraded = set(pick_upgrade_edges(topo, "shortestpath_count", k))
        cov = compute_path_coverage(expanded_edges, "4", "6", upgraded)
        assert cov["path_edges_upgraded"] >= prev_upgraded
        assert cov["path_upgraded_fraction"] >= prev_frac
        prev_upgraded = cov["path_edges_upgraded"]
        prev_frac = cov["path_upgraded_fraction"]
