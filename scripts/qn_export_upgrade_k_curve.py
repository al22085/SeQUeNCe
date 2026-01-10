"""Export upgrade-k frontier curve metrics (linearity / curvature)."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np


def parse_args():
    p = argparse.ArgumentParser(description="Export upgrade-k frontier curvature metrics.")
    p.add_argument("--pair-frontier", type=Path, required=True, help="robust_frontier_pairs.csv from robustness run")
    p.add_argument("--out-csv", type=Path, required=True, help="Where to write upgrade_k_curve_numbers.csv")
    p.add_argument("--pairs-csv", type=Path, default=None, help="Pairs CSV to annotate labels/distances.")
    p.add_argument("--base-strategy", type=str, default="BK")
    p.add_argument("--curve-strategy", type=str, default="EQT")
    p.add_argument("--target", type=float, default=0.9)
    p.add_argument("--eta", type=float, default=0.9)
    p.add_argument("--kbits", type=float, default=1.0)
    p.add_argument("--upgrade-ks", type=str, default="0,3,7,21")
    p.add_argument("--load-max", type=float, default=None, help="Optional load_max used in frontier search for clipping flag.")
    p.add_argument("--curve-points-csv", type=Path, default=None, help="Optional curve_points.csv output path.")
    p.add_argument("--curve-metrics-csv", type=Path, default=None, help="Optional curve_metrics.csv output path.")
    p.add_argument("--topology-id", type=str, default="")
    p.add_argument("--upgrade-policy", type=str, default="")
    p.add_argument("--r2-threshold", type=float, default=0.98)
    p.add_argument("--curvature-threshold", type=float, default=0.01)
    return p.parse_args()


def load_rows(path: Path) -> List[Dict]:
    with path.open() as f:
        return list(csv.DictReader(f))


def load_pair_meta(path: Path | None) -> Dict[str, Dict[str, str]]:
    if not path:
        return {}
    with path.open() as f:
        rows = list(csv.DictReader(f))
    meta = {}
    for r in rows:
        src = r.get("src_node") or r.get("src") or r.get("src_id")
        dst = r.get("dst_node") or r.get("dst") or r.get("dst_id")
        if not src or not dst:
            continue
        key = f"{src}-{dst}"
        meta[key] = r
        meta[f"{dst}-{src}"] = r
    return meta


def main():
    args = parse_args()
    rows = load_rows(args.pair_frontier)
    pair_meta = load_pair_meta(args.pairs_csv)
    ks = [int(x) for x in args.upgrade_ks.split(",") if x]
    ks_sorted = sorted(ks)
    if not ks_sorted:
        raise SystemExit("upgrade-ks must include at least one value")
    kmax = ks_sorted[-1]

    def pick_vals(strategy: str, k: int, pair: Tuple[str, str] | None = None) -> List[float]:
        vals = [
            float(r["frontier_load"])
            for r in rows
            if float(r["eta"]) == args.eta
            and float(r["target"]) == args.target
            and float(r["kbits"]) == args.kbits
            and r["strategy"] == strategy
            and int(r["upgrade_k"]) == k
            and (pair is None or r["pair"] == f"{pair[0]}-{pair[1]}")
        ]
        return vals

    def curve_for_pair(pair: Tuple[str, str]):
        bk0_vals = pick_vals(args.base_strategy, ks_sorted[0], pair)
        if not bk0_vals:
            return None
        bk0 = float(np.median(bk0_vals))
        eqt_vals = {k: pick_vals(args.curve_strategy, k, pair) for k in ks_sorted}
        if any(not v for v in eqt_vals.values()):
            return None
        eqt_frontiers = {k: float(np.median(v)) for k, v in eqt_vals.items()}
        return bk0, eqt_frontiers

    pair_ids = sorted({tuple(r["pair"].split("-")) for r in rows})
    results = []
    curve_points = []
    metrics_rows = []
    for pair in pair_ids:
        curve = curve_for_pair(pair)
        if not curve:
            continue
        bk0, eqt_frontiers = curve
        meta = pair_meta.get(f"{pair[0]}-{pair[1]}", {})
        ratios = {k: (eqt_frontiers[k] / bk0 if bk0 > 0 else 0.0) for k in ks_sorted}
        base_k = ks_sorted[0]
        def frontier_at(k: int) -> float:
            return eqt_frontiers.get(k, eqt_frontiers[base_k])
        s03 = (frontier_at(3) - frontier_at(base_k)) / 3 if 3 in ks_sorted else 0.0
        s37 = (frontier_at(7) - frontier_at(3)) / 4 if 7 in ks_sorted and 3 in ks_sorted else 0.0
        s721 = (frontier_at(21) - frontier_at(7)) / 14 if 21 in ks_sorted and 7 in ks_sorted else 0.0
        clipped = False
        if args.load_max is not None:
            threshold = 0.95 * args.load_max
            clipped = any(v >= threshold for v in eqt_frontiers.values()) or bk0 >= threshold
        # curve points for this pair
        for k in ks_sorted:
            frac = k / kmax if kmax > 0 else 0.0
            curve_points.append(
                {
                    "topology_id": args.topology_id,
                    "upgrade_policy": args.upgrade_policy,
                    "pair": f"{pair[0]}-{pair[1]}",
                    "label": meta.get("label", ""),
                    "target_km": meta.get("target_km", ""),
                    "sp_km": meta.get("sp_km", ""),
                    "abs_error_km": meta.get("abs_error_km", ""),
                    "upgrade_k": k,
                    "upgraded_fraction": frac,
                    "bk0": bk0,
                    "eqt_frontier": eqt_frontiers[k],
                    "ratio_vs_bk0": ratios[k],
                }
            )
        # metrics
        x = np.array([k / kmax if kmax > 0 else 0.0 for k in ks_sorted], dtype=float)
        y = np.array([ratios[k] for k in ks_sorted], dtype=float)
        if len(y) >= 2:
            coeffs = np.polyfit(x, y, 1)
            y_hat = np.polyval(coeffs, x)
            ss_res = float(np.sum((y - y_hat) ** 2))
            ss_tot = float(np.sum((y - np.mean(y)) ** 2))
            r2 = 1.0 if ss_tot == 0 else 1.0 - ss_res / ss_tot
        else:
            r2 = 1.0
        if len(y) >= 3:
            second = [y[i + 1] - 2 * y[i] + y[i - 1] for i in range(1, len(y) - 1)]
            curvature = float(np.mean(np.abs(second)))
        else:
            curvature = 0.0
        classification = "approximately_linear" if (r2 >= args.r2_threshold and curvature <= args.curvature_threshold) else "nonlinear"
        metrics_rows.append(
            {
                "topology_id": args.topology_id,
                "upgrade_policy": args.upgrade_policy,
                "pair": f"{pair[0]}-{pair[1]}",
                "label": meta.get("label", ""),
                "target_km": meta.get("target_km", ""),
                "sp_km": meta.get("sp_km", ""),
                "abs_error_km": meta.get("abs_error_km", ""),
                "kmax": kmax,
                "r2": r2,
                "curvature": curvature,
                "classification": classification,
                "ratio_k21": ratios.get(21, ""),
                "clipped": clipped,
            }
        )
        results.append(
            {
                "pair": f"{pair[0]}-{pair[1]}",
                "bk0": bk0,
                **{f"eqt{k}": eqt_frontiers[k] for k in ks_sorted},
                **{f"ratio{k}": ratios[k] for k in ks_sorted},
                "s03": s03,
                "s37": s37,
                "s721": s721,
                "c1": s37 - s03,
                "c2": s721 - s37,
                "clipped": clipped,
            }
        )

    # aggregate median and worst-case (min) across pairs
    def agg_value(key: str, func):
        vals = [r[key] for r in results if key in r]
        return func(vals) if vals else 0.0

    agg_rows = []
    if results:
        for agg_name, func in (("median", np.median), ("worst_case", np.min)):
            row = {"pair": agg_name}
            for key in ["bk0", *(f"eqt{k}" for k in ks_sorted), *(f"ratio{k}" for k in ks_sorted), "s03", "s37", "s721", "c1", "c2", "clipped"]:
                row[key] = float(func([r[key] for r in results]))
            agg_rows.append(row)

    # aggregated curve points + metrics
    if results:
        for agg_name, func in (("median", np.median), ("worst_case", np.min)):
            agg_curve = {}
            for k in ks_sorted:
                vals = [r[f"ratio{k}"] for r in results]
                agg_curve[k] = float(func(vals))
            for k in ks_sorted:
                frac = k / kmax if kmax > 0 else 0.0
                curve_points.append(
                    {
                        "topology_id": args.topology_id,
                        "upgrade_policy": args.upgrade_policy,
                        "pair": agg_name,
                        "label": agg_name,
                        "target_km": "",
                        "sp_km": "",
                        "abs_error_km": "",
                        "upgrade_k": k,
                        "upgraded_fraction": frac,
                        "bk0": float(func([r["bk0"] for r in results])),
                        "eqt_frontier": float(func([r[f"eqt{k}"] for r in results])),
                        "ratio_vs_bk0": agg_curve[k],
                    }
                )
            x = np.array([k / kmax if kmax > 0 else 0.0 for k in ks_sorted], dtype=float)
            y = np.array([agg_curve[k] for k in ks_sorted], dtype=float)
            if len(y) >= 2:
                coeffs = np.polyfit(x, y, 1)
                y_hat = np.polyval(coeffs, x)
                ss_res = float(np.sum((y - y_hat) ** 2))
                ss_tot = float(np.sum((y - np.mean(y)) ** 2))
                r2 = 1.0 if ss_tot == 0 else 1.0 - ss_res / ss_tot
            else:
                r2 = 1.0
            if len(y) >= 3:
                second = [y[i + 1] - 2 * y[i] + y[i - 1] for i in range(1, len(y) - 1)]
                curvature = float(np.mean(np.abs(second)))
            else:
                curvature = 0.0
            classification = "approximately_linear" if (r2 >= args.r2_threshold and curvature <= args.curvature_threshold) else "nonlinear"
            metrics_rows.append(
                {
                    "topology_id": args.topology_id,
                    "upgrade_policy": args.upgrade_policy,
                    "pair": agg_name,
                    "label": agg_name,
                    "target_km": "",
                    "sp_km": "",
                    "abs_error_km": "",
                    "kmax": kmax,
                    "r2": r2,
                    "curvature": curvature,
                    "classification": classification,
                    "ratio_k21": agg_curve.get(21, ""),
                    "clipped": float(func([r["clipped"] for r in results])) > 0.0,
                }
            )

    out_path = args.out_csv
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "pair",
        "bk0",
        *(f"eqt{k}" for k in ks_sorted),
        *(f"ratio{k}" for k in ks_sorted),
        "s03",
        "s37",
        "s721",
        "c1",
        "c2",
        "clipped",
    ]
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results + agg_rows:
            writer.writerow(r)
    print(f"Wrote upgrade-k curve numbers to {out_path}")
    if agg_rows:
        print("Aggregated (median/worst_case):")
        for r in agg_rows:
            print(r)

    if args.curve_points_csv:
        args.curve_points_csv.parent.mkdir(parents=True, exist_ok=True)
        with args.curve_points_csv.open("w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "topology_id",
                    "upgrade_policy",
                    "pair",
                    "label",
                    "target_km",
                    "sp_km",
                    "abs_error_km",
                    "upgrade_k",
                    "upgraded_fraction",
                    "bk0",
                    "eqt_frontier",
                    "ratio_vs_bk0",
                ],
            )
            writer.writeheader()
            writer.writerows(curve_points)
        print(f"Wrote curve points to {args.curve_points_csv}")

    if args.curve_metrics_csv:
        args.curve_metrics_csv.parent.mkdir(parents=True, exist_ok=True)
        with args.curve_metrics_csv.open("w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "topology_id",
                    "upgrade_policy",
                    "pair",
                    "label",
                    "target_km",
                    "sp_km",
                    "abs_error_km",
                    "kmax",
                    "r2",
                    "curvature",
                    "classification",
                    "ratio_k21",
                    "clipped",
                ],
            )
            writer.writeheader()
            writer.writerows(metrics_rows)
        print(f"Wrote curve metrics to {args.curve_metrics_csv}")


if __name__ == "__main__":
    main()
