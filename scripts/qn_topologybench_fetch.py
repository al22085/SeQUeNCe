"""CLI wrapper to fetch TopologyBench archive using pinned manifest."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sequence.qn.topologybench_fetch import ensure_topologybench_zip


def parse_args():
    p = argparse.ArgumentParser(description="Fetch TopologyBench archive using pinned manifest.")
    p.add_argument("--topologybench-zip", type=Path, default=None, help="Local zip path to use.")
    p.add_argument("--manifest", type=Path, default=None, help="Manifest JSON path override.")
    p.add_argument("--no-download", action="store_true", help="Offline mode; do not download.")
    p.add_argument("--force-download", action="store_true", help="Force re-download from the pinned manifest.")
    p.add_argument("--no-copy", action="store_true", help="Do not copy a provided zip into ./data/topologybench/.")
    return p.parse_args()


def main():
    args = parse_args()
    path = ensure_topologybench_zip(
        manifest_path=args.manifest,
        zip_path=args.topologybench_zip,
        no_download=args.no_download,
        copy_into_data=not args.no_copy,
        force_download=args.force_download,
    )
    print(path)


if __name__ == "__main__":
    main()
