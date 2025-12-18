import csv
from pathlib import Path

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
