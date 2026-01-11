"""Deprecated wrapper for Tier2 key-findings generation."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def main() -> None:
    sys.stderr.write(
        "DEPRECATED: use scripts/qn_generate_tier2_key_findings.py instead.\n"
    )
    target = Path(__file__).with_name("qn_generate_tier2_key_findings.py")
    spec = importlib.util.spec_from_file_location("qn_generate_tier2_key_findings", target)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Cannot load {target}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.main()


if __name__ == "__main__":
    main()
