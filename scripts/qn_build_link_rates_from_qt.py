"""Build per-link key-generation rate maps from QT outputs."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Dict, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.qn_topologies import nsfnet_edges, nsfnet_topology


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build link-rate map from QT outputs.")
    p.add_argument("--in", dest="in_path", type=Path, required=True, help="QT output file (CSV or JSON).")
    p.add_argument("--prob-column", type=str, default="success_prob", help="Column/key containing success probability.")
    p.add_argument("--strategy", type=str, default="", help="Optional strategy filter for multi-strategy inputs.")
    p.add_argument("--attempt-rate-hz", type=float, default=1e6)
    p.add_argument("--key-bits-per-success", type=float, default=1.0)
    p.add_argument("--topology", choices=["nsfnet"], default="nsfnet")
    p.add_argument("--upgrade-topk", type=int, default=0, help="If >0, only top-k edges are upgraded.")
    p.add_argument("--upgrade-edges", type=str, default="", help="Comma list of edges A-B to upgrade.")
    p.add_argument("--upgrade-mult", type=float, default=1.0, help="Multiplier for upgraded edges.")
    p.add_argument("--upgraded-only", action="store_true", help="If set, non-upgraded edges get 0 rate.")
    p.add_argument("--out-json", type=Path, default=Path("out/link_rates.json"))
    p.add_argument("--out-csv", type=Path, default=None)
    return p.parse_args()


def load_probabilities(args: argparse.Namespace) -> float:
    path = args.in_path
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text())
        rows = data if isinstance(data, list) else data.get("rows") or data.get("data") or []
    else:
        with path.open() as f:
            rows = list(csv.DictReader(f))
    probs = []
    for row in rows:
        if args.strategy and str(row.get("strategy", "")).upper() != args.strategy.upper():
            continue
        try:
            probs.append(float(row[args.prob_column]))
        except Exception:
            continue
    if not probs:
        raise ValueError("No probabilities parsed; check --prob-column/--strategy.")
    return sum(probs) / len(probs)


def edge_usage_counts(topo) -> Dict[Tuple[str, str], int]:
    from collections import defaultdict, deque

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


def main():
    args = parse_args()
    prob = load_probabilities(args)
    rate = args.attempt_rate_hz * prob * args.key_bits_per_success
    topo = nsfnet_topology() if args.topology == "nsfnet" else {}
    edges = [tuple(sorted(e)) for e in nsfnet_edges()] if args.topology == "nsfnet" else []
    rates = {e: rate for e in edges}

    upgrade_edges = []
    if args.upgrade_topk > 0:
        counts = edge_usage_counts(topo)
        ranked = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
        upgrade_edges.extend([edge for edge, _ in ranked[: args.upgrade_topk]])
    if args.upgrade_edges:
        for item in args.upgrade_edges.split(","):
            if not item:
                continue
            a, b = item.split("-")
            upgrade_edges.append(tuple(sorted((a, b))))

    if upgrade_edges:
        if args.upgraded_only:
            rates = {e: (rate * args.upgrade_mult if e in upgrade_edges else 0.0) for e in edges}
        else:
            for e in upgrade_edges:
                if e in rates:
                    rates[e] *= args.upgrade_mult

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps({f"{a}-{b}": v for (a, b), v in rates.items()}, indent=2))
    if args.out_csv:
        args.out_csv.parent.mkdir(parents=True, exist_ok=True)
        with args.out_csv.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["edge", "rate_bps"])
            for (a, b), v in rates.items():
                writer.writerow([f"{a}-{b}", v])
    print(f"Wrote link-rate map to {args.out_json}")
    if args.out_csv:
        print(f"Wrote CSV to {args.out_csv}")


if __name__ == "__main__":
    main()
