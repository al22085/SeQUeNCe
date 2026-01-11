"""Verify and safely unpack Tier2 paper bundle."""

from __future__ import annotations

import argparse
import subprocess
import sys
import zipfile
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Verify and unpack Tier2 paper bundle safely.")
    p.add_argument("--bundle", type=Path, required=True)
    p.add_argument(
        "--out-dir",
        type=Path,
        default=Path("tier2_paper_bundle_extracted"),
        help="Output directory for extracted bundle.",
    )
    p.add_argument("--overwrite", action="store_true", default=False)
    return p.parse_args()


def safe_extract(zf: zipfile.ZipFile, out_dir: Path, overwrite: bool) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_root = out_dir.resolve()
    for name in zf.namelist():
        if name.endswith("/"):
            (out_root / name).mkdir(parents=True, exist_ok=True)
            continue
        dest = (out_root / name).resolve()
        if not str(dest).startswith(str(out_root)):
            raise SystemExit(f"Unsafe path in zip: {name}")
        if dest.exists() and not overwrite:
            raise SystemExit(f"Refusing to overwrite existing file: {dest}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(zf.read(name))


def main() -> None:
    args = parse_args()
    # Run verification first via subprocess to avoid import path issues.
    subprocess.run(
        [
            sys.executable,
            "scripts/qn_verify_tier2_paper_bundle.py",
            "--bundle",
            str(args.bundle),
        ],
        check=True,
    )

    with zipfile.ZipFile(args.bundle) as zf:
        safe_extract(zf, args.out_dir, args.overwrite)

    print(f"Bundle extracted to: {args.out_dir}")
    print(f"- paper_artifacts/README.md: {args.out_dir / 'paper_artifacts' / 'README.md'}")
    print(f"- tables (*.tex): {args.out_dir / 'paper_artifacts' / 'tables'}")
    print(f"- figures (*.png): {args.out_dir / 'paper_artifacts' / 'figures'}")
    print(f"- validation_report.json: {args.out_dir / 'paper_artifacts' / 'validation_report.json'}")


if __name__ == "__main__":
    main()
