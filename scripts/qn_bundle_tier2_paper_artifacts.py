"""Bundle Tier2 paper artifacts and provenance into a single zip with SHA256 manifest."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
MAX_EXTRA_FILE_BYTES = 50 * 1024 * 1024
MAX_EXTRA_TOTAL_BYTES = 200 * 1024 * 1024


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Bundle Tier2 paper artifacts into a single zip.")
    p.add_argument("--root-dir", type=Path, required=True)
    p.add_argument(
        "--bundle-path",
        type=Path,
        default=None,
        help="Output zip path (default: <root>/paper_artifacts_bundle.zip).",
    )
    p.add_argument(
        "--include",
        type=str,
        default="paper_artifacts,metadata,csv,json",
        help="Comma list: paper_artifacts,metadata,csv,json (default: all).",
    )
    return p.parse_args()


def load_csv(path: Path) -> List[Dict[str, str]]:
    with path.open() as f:
        return list(csv.DictReader(f))


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def run_validator(root: Path) -> None:
    subprocess.run(
        ["python", "scripts/qn_validate_tier2_run.py", "--root-dir", str(root)],
        check=True,
        cwd=repo_root(),
    )


def ensure_exporter(root: Path) -> None:
    paper_dir = root / "paper_artifacts"
    if paper_dir.exists():
        required = [
            paper_dir / "latex_include" / "tier2_paper_artifacts.tex",
            paper_dir / "tables" / "table_linearity_summary.tex",
            paper_dir / "figs" / "fig_linearity_overview.png",
        ]
        if all(p.exists() for p in required):
            return
    subprocess.run(
        ["python", "scripts/qn_export_tier2_paper_artifacts.py", "--root-dir", str(root)],
        check=True,
        cwd=repo_root(),
    )


def find_seed_list(root: Path) -> List[int]:
    for path in root.rglob("robust_frontier_raw.csv"):
        rows = load_csv(path)
        if not rows or "seed" not in rows[0]:
            continue
        seeds = sorted({int(r["seed"]) for r in rows if r.get("seed")})
        if seeds:
            return seeds
    return []


def build_run_metadata(root: Path) -> Path:
    meta_path = root / "run_metadata.json"
    if meta_path.exists():
        return meta_path

    chosen = {}
    chosen_path = root / "chosen_tolerance.json"
    if chosen_path.exists():
        chosen = json.loads(chosen_path.read_text())

    summary_path = root / "summary_upgrade_curves.csv"
    rows = load_csv(summary_path) if summary_path.exists() else []
    policies = sorted({r.get("policy", "") for r in rows if r.get("policy")})
    targets = sorted({r.get("target_A", "") for r in rows if r.get("target_A")})
    kbits = sorted({r.get("kbits", "") for r in rows if r.get("kbits")})
    eta = sorted({r.get("eta", "") for r in rows if r.get("eta")})
    seeds = find_seed_list(root)

    meta = {
        "chosen_tolerance": chosen.get("chosen_tolerance"),
        "targets_km": chosen.get("targets_km", []),
        "pairs_per_target": chosen.get("pairs_per_target"),
        "chosen_topologies": chosen.get("chosen_topologies", []),
        "policies": policies,
        "target_A_values": targets,
        "kbits_values": kbits,
        "eta_values": eta,
        "seeds": seeds,
    }
    meta_path.write_text(json.dumps(meta, indent=2))
    return meta_path


def sha256_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def zip_write_bytes(zf: zipfile.ZipFile, arcname: str, data: bytes) -> None:
    info = zipfile.ZipInfo(arcname)
    info.date_time = FIXED_ZIP_TIME
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    zf.writestr(info, data)


def collect_files(root: Path, include: List[str]) -> List[Tuple[Path, str]]:
    include_set = {x.strip() for x in include if x.strip()}
    files: List[Tuple[Path, str]] = []

    def add(path: Path) -> None:
        if not path.exists():
            return
        rel = path.relative_to(root).as_posix()
        files.append((path, rel))

    if "paper_artifacts" in include_set:
        for path in sorted((root / "paper_artifacts").rglob("*")):
            if path.is_file():
                add(path)

    if "metadata" in include_set:
        add(build_run_metadata(root))
        add(root / "chosen_tolerance.json")
        add(root / "topology_selection.json")

    if "csv" in include_set:
        add(root / "summary_upgrade_curves.csv")
        add(root / "line_vs_curve_summary.csv")
        add(root / "tolerance_missing_summary.csv")
        add(root / "analysis_path_coverage" / "path_coverage_thresholds_summary.csv")

    if "json" in include_set:
        add(root / "parallel_report.json")

    # Optional curve points/metrics (size-bounded).
    extra_total = 0
    for path in sorted(root.rglob("curve_points.csv")):
        if path.stat().st_size > MAX_EXTRA_FILE_BYTES:
            continue
        if extra_total + path.stat().st_size > MAX_EXTRA_TOTAL_BYTES:
            break
        add(path)
        extra_total += path.stat().st_size
    for path in sorted(root.rglob("curve_metrics.csv")):
        if path.stat().st_size > MAX_EXTRA_FILE_BYTES:
            continue
        if extra_total + path.stat().st_size > MAX_EXTRA_TOTAL_BYTES:
            break
        add(path)
        extra_total += path.stat().st_size

    # Deduplicate while preserving deterministic order.
    seen = set()
    uniq: List[Tuple[Path, str]] = []
    for path, rel in sorted(files, key=lambda x: x[1]):
        if rel in seen:
            continue
        seen.add(rel)
        uniq.append((path, rel))
    return uniq


def build_bundle_manifest(root: Path, validation: Dict[str, object]) -> Dict[str, object]:
    meta_path = root / "run_metadata.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}

    commit = "unknown"
    try:
        commit = (
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_root())
            .decode()
            .strip()
        )
    except Exception:
        pass
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return {
        "created_at_iso": created_at,
        "root_dir_basename": root.name,
        "git_commit": commit,
        "selected_topologies": meta.get("chosen_topologies", []),
        "chosen_tolerance": meta.get("chosen_tolerance"),
        "policies": meta.get("policies", []),
        "targets_km": meta.get("targets_km", []),
        "seeds": meta.get("seeds", []),
        "validation": {
            "missing_pairs": validation.get("missing_pairs", {}),
            "preflight": validation.get("preflight", {}),
        },
    }


def ensure_bundle_usage_readme(root: Path) -> None:
    readme = root / "paper_artifacts" / "README.md"
    if not readme.exists():
        return
    text = readme.read_text()
    if "Bundle usage" in text:
        return
    addition = "\n".join(
        [
            "",
            "## Bundle usage",
            "1) Verify bundle integrity:",
            "   python scripts/qn_verify_tier2_paper_bundle.py --bundle paper_artifacts_bundle.zip",
            "2) Unpack safely:",
            "   python scripts/qn_unpack_tier2_paper_bundle.py --bundle paper_artifacts_bundle.zip --out-dir <dest>",
            "3) Use paper_artifacts/tables/*.tex and paper_artifacts/figures/*.png in your LaTeX repo.",
            "",
        ]
    )
    readme.write_text(text + addition)


def main() -> None:
    args = parse_args()
    root = args.root_dir
    bundle_path = args.bundle_path or (root / "paper_artifacts_bundle.zip")
    include = args.include.split(",")

    run_validator(root)
    ensure_exporter(root)
    meta_path = build_run_metadata(root)

    validation_path = root / "paper_artifacts" / "validation_report.json"
    validation = json.loads(validation_path.read_text()) if validation_path.exists() else {}
    ensure_bundle_usage_readme(root)

    files = collect_files(root, include)
    if not files:
        raise SystemExit("No files collected for bundling; check --include and root-dir.")

    bundle_manifest = build_bundle_manifest(root, validation)
    manifest_bytes = json.dumps(bundle_manifest, indent=2).encode()

    sha_entries: List[Tuple[str, str]] = []
    for path, rel in files:
        sha_entries.append((rel, sha256_bytes(read_bytes(path))))
    sha_entries.append(("bundle_manifest.json", sha256_bytes(manifest_bytes)))
    sha_lines = [f"{sha}  {rel}" for rel, sha in sorted(sha_entries, key=lambda x: x[0])]

    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path, rel in files:
            zip_write_bytes(zf, rel, read_bytes(path))
        zip_write_bytes(zf, "SHA256SUMS.txt", ("\n".join(sha_lines) + "\n").encode())
        zip_write_bytes(zf, "bundle_manifest.json", manifest_bytes)

    print(f"Bundle written to: {bundle_path}")


if __name__ == "__main__":
    main()
