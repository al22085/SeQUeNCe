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
