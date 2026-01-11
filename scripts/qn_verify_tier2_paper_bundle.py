"""Verify Tier2 paper bundle integrity using SHA256SUMS and print manifest summary."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path
from typing import Dict, List, Tuple


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Verify Tier2 paper bundle integrity.")
    p.add_argument("--bundle", type=Path, required=True)
    p.add_argument("--print-manifest", action="store_true", default=True)
    p.add_argument("--strict", action="store_true", default=True)
    return p.parse_args()


def sha256_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def parse_sha256sums(text: str) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        sha = parts[0]
        path = parts[1]
        mapping[path] = sha
    return mapping


def verify_bundle(bundle: Path, *, print_manifest: bool, strict: bool) -> None:
    if not bundle.exists():
        raise SystemExit(f"Bundle not found: {bundle}")

    with zipfile.ZipFile(bundle) as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]
        if "SHA256SUMS.txt" not in names:
            raise SystemExit("SHA256SUMS.txt missing from bundle")
        if "bundle_manifest.json" not in names:
            raise SystemExit("bundle_manifest.json missing from bundle")

        sha_text = zf.read("SHA256SUMS.txt").decode("utf-8")
        listed = parse_sha256sums(sha_text)

        mismatches: List[str] = []
        missing: List[str] = []
        for path, expected in listed.items():
            if path not in names:
                missing.append(path)
                continue
            actual = sha256_bytes(zf.read(path))
            if actual != expected:
                mismatches.append(f"{path}: expected {expected} got {actual}")

        extras = []
        if strict:
            allowed = {"SHA256SUMS.txt"}
            for name in names:
                if name in listed or name in allowed:
                    continue
                extras.append(name)

        if missing or mismatches or extras:
            parts = []
            if missing:
                parts.append(f"missing={missing}")
            if mismatches:
                parts.append(f"mismatches={mismatches}")
            if extras:
                parts.append(f"extras={extras}")
            raise SystemExit("Bundle verification failed: " + "; ".join(parts))

        manifest = json.loads(zf.read("bundle_manifest.json").decode("utf-8"))
        if print_manifest:
            pre = manifest.get("validation", {}).get("preflight", {})
            missing_pairs = manifest.get("validation", {}).get("missing_pairs", {})
            print("Bundle manifest summary:")
            print(f"- git_commit: {manifest.get('git_commit')}")
            print(f"- root_dir_basename: {manifest.get('root_dir_basename')}")
            print(f"- chosen_tolerance: {manifest.get('chosen_tolerance')}")
            print(f"- selected_topologies: {manifest.get('selected_topologies')}")
            print(f"- missing_pairs: {missing_pairs}")
            print(
                f"- preflight: active_workers={pre.get('active_workers')} "
                f"aggregate_cpu={pre.get('aggregate_cpu')} expected_cpu={pre.get('expected_cpu')}"
            )

    print("Bundle verification OK.")


def main() -> None:
    args = parse_args()
    verify_bundle(args.bundle, print_manifest=args.print_manifest, strict=args.strict)


if __name__ == "__main__":
    main()
