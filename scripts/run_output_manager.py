"""Utility to organize simulation outputs under out/runs/<run_id>/."""

from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

RUNS_DEFAULT = Path("out/runs")
RAW_DIRNAME = "raw"
PLOTS_DIRNAME = "plots"

RAW_EXTS = {".csv", ".json"}
PLOT_EXTS = {".png", ".pdf", ".svg", ".jpg", ".jpeg", ".eps", ".tif", ".tiff", ".gif"}

_SIMPLE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")


def sanitize_label(label: str) -> str:
    cleaned = re.sub(r"\s+", "-", label.strip().lower())
    cleaned = re.sub(r"[^a-z0-9_-]", "-", cleaned)
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    cleaned = cleaned.strip("-_")
    return cleaned or "run"


def generate_run_id(label: str, now: datetime | None = None) -> str:
    timestamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    return f"{timestamp}_{sanitize_label(label)}"


def unique_run_dir(out_root: Path, run_id: str) -> Path:
    candidate = out_root / run_id
    if not candidate.exists():
        return candidate
    suffix = 2
    while True:
        candidate = out_root / f"{run_id}_{suffix}"
        if not candidate.exists():
            return candidate
        suffix += 1


def parse_param_pairs(pairs: Iterable[str]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for pair in pairs:
        if "=" not in pair:
            raise ValueError(f"Invalid param '{pair}'. Expected key=value.")
        key, raw = pair.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Invalid param '{pair}'. Empty key.")
        params[key] = parse_param_value(raw.strip())
    return params


def parse_param_value(raw: str) -> Any:
    if raw == "":
        return ""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def format_yaml_key(key: Any) -> str:
    text = str(key)
    if _SIMPLE_KEY.match(text):
        return text
    return json.dumps(text)


def format_yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, Path):
        value = str(value)
    return json.dumps(str(value))


def dump_yaml_lines(data: Any, indent: int = 0) -> list[str]:
    space = "  " * indent
    if isinstance(data, dict):
        lines: list[str] = []
        for key, value in data.items():
            key_text = format_yaml_key(key)
            if isinstance(value, (dict, list)):
                lines.append(f"{space}{key_text}:")
                lines.extend(dump_yaml_lines(value, indent + 1))
            else:
                lines.append(f"{space}{key_text}: {format_yaml_scalar(value)}")
        return lines
    if isinstance(data, list):
        lines = []
        for item in data:
            if isinstance(item, (dict, list)):
                lines.append(f"{space}-")
                lines.extend(dump_yaml_lines(item, indent + 1))
            else:
                lines.append(f"{space}- {format_yaml_scalar(item)}")
        return lines
    return [f"{space}{format_yaml_scalar(data)}"]


def write_yaml(path: Path, data: Any) -> None:
    content = "\n".join(dump_yaml_lines(data)) + "\n"
    path.write_text(content, encoding="utf-8")


def find_git_root(start: Path) -> Path | None:
    start_dir = start if start.is_dir() else start.parent
    try:
        result = subprocess.run(
            ["git", "-C", str(start_dir), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None
    root = result.stdout.strip()
    return Path(root) if root else None


def git_commit_hash(repo_root: Path | None) -> str:
    if repo_root is None:
        return "unknown"
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return "unknown"
    return result.stdout.strip() or "unknown"


def pip_freeze() -> str:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "freeze"],
            check=True,
            capture_output=True,
            text=True,
        )
        output = result.stdout.strip()
        return output if output else "(empty)"
    except Exception:
        try:
            import importlib.metadata as metadata
        except Exception:
            return "pip freeze unavailable"
        lines = []
        for dist in metadata.distributions():
            name = dist.metadata.get("Name") or dist.name
            lines.append(f"{name}=={dist.version}")
        lines.sort(key=lambda x: x.lower())
        return "\n".join(lines)


def resolve_sequence_repo(sequence_repo: Path | None, repo_root: Path | None) -> Path | None:
    if sequence_repo is not None:
        return sequence_repo
    if repo_root is not None:
        candidate = repo_root / "sequence" / "__init__.py"
        if candidate.exists():
            return repo_root
    try:
        import sequence  # type: ignore
    except Exception:
        return None
    return find_git_root(Path(sequence.__file__).resolve())


def write_env(path: Path, repo_root: Path | None, sequence_repo: Path | None) -> None:
    repo_hash = git_commit_hash(repo_root)
    sequence_hash = git_commit_hash(sequence_repo)
    lines = [
        f"created_at: {datetime.now().isoformat()}",
        f"python_version: {sys.version}",
        f"python_executable: {sys.executable}",
        f"repo_root: {repo_root or 'unknown'}",
        f"repo_commit: {repo_hash}",
        f"sequence_repo: {sequence_repo or 'unknown'}",
        f"sequence_commit: {sequence_hash}",
        "",
        "pip_freeze:",
        pip_freeze(),
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def unique_destination(dest: Path) -> Path:
    if not dest.exists():
        return dest
    stem = dest.stem
    suffix = dest.suffix
    counter = 2
    while True:
        candidate = dest.with_name(f"{stem}_{counter}{suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def stage_file(src: Path, dest: Path, mode: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if mode == "copy":
        shutil.copy2(src, dest)
    elif mode == "move":
        shutil.move(str(src), str(dest))
    elif mode == "hardlink":
        os.link(src, dest)
    elif mode == "symlink":
        os.symlink(src, dest)
    else:
        raise ValueError(f"Unsupported mode: {mode}")


def expand_globs(items: Iterable[str]) -> list[Path]:
    expanded: list[Path] = []
    for item in items:
        matches = glob.glob(item, recursive=True)
        if matches:
            expanded.extend(Path(m) for m in matches)
        else:
            expanded.append(Path(item))
    return expanded


def collect_files(root: Path, allowed_exts: set[str] | None) -> list[Path]:
    if root.is_file():
        return [root]
    if root.is_dir():
        files = []
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if allowed_exts is not None and path.suffix.lower() not in allowed_exts:
                continue
            files.append(path)
        return files
    raise FileNotFoundError(f"Missing path: {root}")


def stage_inputs(
    inputs: Iterable[Path],
    dest_root: Path,
    mode: str,
    allowed_exts: set[str] | None,
) -> None:
    for src in inputs:
        if src.is_file():
            dest = unique_destination(dest_root / src.name)
            stage_file(src, dest, mode)
            continue
        if src.is_dir():
            for file_path in collect_files(src, allowed_exts):
                rel = file_path.relative_to(src)
                dest = dest_root / src.name / rel
                dest = unique_destination(dest)
                stage_file(file_path, dest, mode)
            continue
        raise FileNotFoundError(f"Missing path: {src}")


def ensure_out_readme(out_dir: Path, force: bool = False) -> None:
    readme_path = out_dir / "README.md"
    if readme_path.exists() and not force:
        return
    content = "\n".join(
        [
            "# Output Guide",
            "",
            "Simulation outputs are organized by run under `out/runs/<run_id>/`.",
            "Run IDs use the format `YYYYmmdd_HHMMSS_<label>`.",
            "",
            "Each run directory contains:",
            "- config.yaml: input parameters for the run.",
            "- env.txt: environment snapshot (python version, pip package list, git commit hashes).",
            "- metrics.csv: aggregated metrics.",
            "- raw/: raw csv/json results (if provided).",
            "- plots/: figures (if provided).",
            "",
            "Create a run directory with:",
            "python scripts/run_output_manager.py --label <label> --config-file <config.json|yaml> "
            "--metrics-file <metrics.csv|json> [--raw ...] [--plot ...]",
            "",
            "For large outputs, consider `--raw-mode hardlink` or `--raw-mode symlink` to avoid copying.",
            "",
        ]
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    readme_path.write_text(content, encoding="utf-8")


def metrics_rows_from_json(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        rows = []
        for item in data:
            if not isinstance(item, dict):
                raise ValueError("metrics JSON list entries must be objects.")
            rows.append(item)
        return rows
    if isinstance(data, dict):
        return [data]
    raise ValueError("metrics JSON must be an object or list of objects.")


def write_metrics_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: list[str] = []
    seen = set()
    for row in rows:
        for key in row.keys():
            if key not in seen:
                fieldnames.append(key)
                seen.add(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            formatted = {}
            for key in fieldnames:
                value = row.get(key, "")
                if isinstance(value, (dict, list)):
                    formatted[key] = json.dumps(value)
                else:
                    formatted[key] = value
            writer.writerow(formatted)


def load_config(
    config_file: Path | None,
    config_json: str | None,
    params: dict[str, Any],
) -> tuple[Any, Path | None]:
    data: Any = None
    if config_file is not None:
        if not config_file.exists():
            raise FileNotFoundError(f"Missing config file: {config_file}")
        suffix = config_file.suffix.lower()
        if suffix in {".yaml", ".yml"}:
            if config_json or params:
                raise ValueError("Cannot merge params with YAML config without a YAML parser.")
            return None, config_file
        if suffix == ".json":
            data = json.loads(config_file.read_text(encoding="utf-8"))
        else:
            raise ValueError("Config file must be JSON or YAML.")
    if config_json:
        parsed = json.loads(config_json)
        if data is None:
            data = parsed
        elif isinstance(data, dict) and isinstance(parsed, dict):
            merged = dict(data)
            merged.update(parsed)
            data = merged
        else:
            data = parsed
    if params:
        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise ValueError("Params require the config to be an object.")
        data = dict(data)
        data.update(params)
    if data is None and config_file is None:
        raise ValueError("Config is required.")
    return data, None


def load_metrics(metrics_file: Path | None, metrics_json: str | None) -> tuple[list[dict[str, Any]] | None, Path | None]:
    if metrics_file is not None:
        if not metrics_file.exists():
            raise FileNotFoundError(f"Missing metrics file: {metrics_file}")
        suffix = metrics_file.suffix.lower()
        if suffix == ".json":
            data = json.loads(metrics_file.read_text(encoding="utf-8"))
            return metrics_rows_from_json(data), None
        return None, metrics_file
    if metrics_json is not None:
        data = json.loads(metrics_json)
        return metrics_rows_from_json(data), None
    raise ValueError("Metrics are required.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Organize simulation outputs under out/runs/<run_id>.")
    parser.add_argument("--label", required=True, help="Short label for the run_id.")
    parser.add_argument("--out-root", type=Path, default=RUNS_DEFAULT, help="Root output dir (default: out/runs).")
    parser.add_argument("--config-file", type=Path, help="Config file path (JSON or YAML).")
    parser.add_argument("--config-json", type=str, help="Config JSON string.")
    parser.add_argument("--param", action="append", default=[], help="Extra config entries (key=value).")
    parser.add_argument("--metrics-file", type=Path, help="Metrics file path (CSV or JSON).")
    parser.add_argument("--metrics-json", type=str, help="Metrics JSON string.")
    parser.add_argument("--raw", action="append", default=[], help="Raw result file/dir (csv/json).")
    parser.add_argument("--plot", action="append", default=[], help="Plot file/dir (figures).")
    parser.add_argument(
        "--raw-mode",
        choices=["copy", "move", "hardlink", "symlink"],
        default="copy",
        help="How to store raw/plot files (default: copy).",
    )
    parser.add_argument("--sequence-repo", type=Path, help="Path to SeQUeNCe git repo (optional).")
    parser.add_argument("--repo-root", type=Path, help="Path to this repo root (optional).")
    parser.add_argument("--force-readme", action="store_true", help="Overwrite out/README.md if it exists.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        params = parse_param_pairs(args.param)
        config_data, config_copy = load_config(args.config_file, args.config_json, params)
        metrics_rows, metrics_copy = load_metrics(args.metrics_file, args.metrics_json)
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        parser.error(str(exc))

    out_root: Path = args.out_root
    run_id = generate_run_id(args.label)
    run_dir = unique_run_dir(out_root, run_id)
    run_dir.mkdir(parents=True, exist_ok=False)

    config_path = run_dir / "config.yaml"
    if config_copy is not None:
        shutil.copy2(config_copy, config_path)
    else:
        write_yaml(config_path, config_data)

    repo_root = args.repo_root or find_git_root(Path.cwd())
    sequence_repo = resolve_sequence_repo(args.sequence_repo, repo_root)
    write_env(run_dir / "env.txt", repo_root, sequence_repo)

    metrics_path = run_dir / "metrics.csv"
    if metrics_copy is not None:
        shutil.copy2(metrics_copy, metrics_path)
    else:
        write_metrics_csv(metrics_path, metrics_rows or [])

    raw_inputs = expand_globs(args.raw)
    if raw_inputs:
        raw_dir = run_dir / RAW_DIRNAME
        stage_inputs(raw_inputs, raw_dir, args.raw_mode, RAW_EXTS)

    plots_dir = run_dir / PLOTS_DIRNAME
    plots_dir.mkdir(parents=True, exist_ok=True)
    plot_inputs = expand_globs(args.plot)
    if plot_inputs:
        stage_inputs(plot_inputs, plots_dir, args.raw_mode, PLOT_EXTS)

    ensure_out_readme(Path("out"), force=args.force_readme)

    print(run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
