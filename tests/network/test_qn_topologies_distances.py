import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.qn_topologies import load_default_nsfnet_distances


def test_default_nsfnet_distances_non_uniform():
    dist = load_default_nsfnet_distances()
    assert dist, "default NSFNET distance map missing"
    values = list(dist.values())
    assert len(set(values)) > 1, "distances should be non-uniform"
