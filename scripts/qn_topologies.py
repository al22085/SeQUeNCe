import csv
import math
from pathlib import Path
from typing import Iterable, List, Tuple
from collections import defaultdict, deque

NSFNET_NODES = [
    "1",
    "2",
    "3",
    "4",
    "5",
    "6",
    "7",
    "8",
    "9",
    "10",
    "11",
    "12",
    "13",
    "14",
]

# Simplified adjacency (undirected)
NSFNET_EDGES = [
    ("1", "2"),
    ("1", "3"),
    ("2", "3"),
    ("2", "4"),
    ("3", "5"),
    ("4", "5"),
    ("4", "6"),
    ("5", "7"),
    ("6", "7"),
    ("6", "8"),
    ("7", "9"),
    ("8", "9"),
    ("8", "10"),
    ("9", "11"),
    ("10", "11"),
    ("10", "12"),
    ("11", "13"),
    ("12", "13"),
    ("12", "14"),
    ("13", "14"),
    ("5", "6"),
]


def nsfnet_topology():
    topo = {n: [] for n in NSFNET_NODES}
    for a, b in NSFNET_EDGES:
        topo[a].append(b)
        topo[b].append(a)
    return topo


def nsfnet_edges():
    return list(NSFNET_EDGES)


def load_edge_distances_csv(path: Path):
    dist = {}
    with path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            u, v = row["u"], row["v"]
            if "distance_m" in row:
                d = float(row["distance_m"])
            elif "distance_km" in row:
                d = float(row["distance_km"]) * 1000.0
            else:
                raise KeyError("distance_m or distance_km column required")
            dist[tuple(sorted((u, v)))] = d
    return dist


def load_graph_from_edge_csv(path: Path):
    """Load an undirected graph + distance map from edge CSV (u,v,length_km or distance_km)."""
    dist = load_edge_distances_csv(path)
    topo = build_topology_from_dist_map(dist)
    return topo, dist


def build_topology_from_dist_map(dist_map):
    topo = {}
    for u, v in dist_map.keys():
        topo.setdefault(u, []).append(v)
        topo.setdefault(v, []).append(u)
    return topo


def load_distance_dataset(dataset_id: str):
    base = Path(__file__).resolve().parents[1] / "data"
    if dataset_id == "topologybench_nsfnet13":
        path = base / "nsfnet_distances_topologybench.csv"
        if not path.exists():
            raise FileNotFoundError(f"{path} missing; run qn_import_nsfnet_distances_from_topologybench.py")
    else:
        path = base / "nsfnet_distances.csv"
    dist = {}
    if path.exists():
        with path.open() as f:
            reader = csv.DictReader(f)
            for row in reader:
                dist[tuple(sorted((row["u"], row["v"])))] = float(row["distance_km"]) * 1000.0
    return dist


def subdivide_edges(dist_map, segment_length_km: float | None = None, segments_per_edge: int | None = None):
    """Subdivide each edge into shorter segments with virtual nodes."""
    if segment_length_km is None and segments_per_edge is None:
        segment_length_km = 50.0
    expanded_edges = []
    mapping = {}
    virtual_nodes = set()
    for (u, v), dist_m in dist_map.items():
        dist_km = dist_m / 1000.0
        if segments_per_edge:
            segs = max(1, segments_per_edge)
        else:
            segs = max(1, int(math.ceil(dist_km / segment_length_km)))
        seg_len_km = dist_km / segs
        prev = u
        mapping[(u, v)] = []
        for i in range(segs - 1):
            node = f"{u}-{v}-seg{i}"
            virtual_nodes.add(node)
            nxt = node
            expanded_edges.append((prev, nxt, seg_len_km * 1000.0, (u, v)))
            mapping[(u, v)].append((prev, nxt))
            prev = nxt
        expanded_edges.append((prev, v, seg_len_km * 1000.0, (u, v)))
        mapping[(u, v)].append((prev, v))
    return expanded_edges, mapping, virtual_nodes


def edge_usage_counts(topo):
    counts = defaultdict(int)
    nodes = list(topo.keys())
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            src, dst = nodes[i], nodes[j]
            q = deque([[src]])
            visited = {src}
            path = None
            while q:
                p = q.popleft()
                n = p[-1]
                if n == dst:
                    path = p
                    break
                for nei in topo[n]:
                    if nei not in visited:
                        visited.add(nei)
                        q.append(p + [nei])
            if not path:
                continue
            for k in range(len(path) - 1):
                edge = tuple(sorted((path[k], path[k + 1])))
                counts[edge] += 1
    return counts


def pick_upgrade_edges(topo, policy: str, k: int) -> List[Tuple[str, str]]:
    if k <= 0:
        return []
    if policy in ("shortestpath_count", "betweenness"):
        ranked = sorted(edge_usage_counts(topo).items(), key=lambda x: (-x[1], x[0]))
        return [e for e, _ in ranked[:k]]
    return []


def orig_edges_in_path(path_edges: List[Tuple[str, str, float, Tuple[str, str]]]) -> List[Tuple[str, str]]:
    """Return unique original edges in path order (sorted tuple per edge)."""
    out = []
    seen = set()
    for _, _, _, orig in path_edges:
        edge = tuple(sorted(orig))
        if edge not in seen:
            seen.add(edge)
            out.append(edge)
    return out


def edge_usage_counts_for_pairs(expanded_edges, pairs: List[Tuple[str, str]]):
    counts = defaultdict(int)
    for src, dst in pairs:
        path = shortest_path_edges(expanded_edges, src, dst)
        for edge in orig_edges_in_path(path):
            counts[edge] += 1
    return counts


def expanded_nodes(expanded_edges: Iterable[Tuple[str, str, float, Tuple[str, str]]]) -> List[str]:
    nodes = set()
    for a, b, *_ in expanded_edges:
        nodes.add(a)
        nodes.add(b)
    return list(nodes)


def shortest_path_edges(expanded_edges: List[Tuple[str, str, float, Tuple[str, str]]], src: str, dst: str):
    """Dijkstra on expanded graph; returns list of (u,v,dist_m,orig_edge) from src to dst."""
    adj = {}
    for a, b, dist_m, orig in expanded_edges:
        adj.setdefault(a, []).append((b, dist_m, orig))
        adj.setdefault(b, []).append((a, dist_m, orig))
    import heapq

    pq = [(0.0, src, [])]
    seen = set()
    while pq:
        d, node, path = heapq.heappop(pq)
        if node in seen:
            continue
        seen.add(node)
        if node == dst:
            return path
        for nei, w, orig in adj.get(node, []):
            if nei not in seen:
                heapq.heappush(pq, (d + w, nei, path + [(node, nei, w, orig)]))
    return []
