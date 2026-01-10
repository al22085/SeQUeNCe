"""Fetch TopologyBench archive using a pinned manifest (repo-local data/)."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import urllib.request
from pathlib import Path


def read_manifest(manifest_path: Path) -> dict:
    if not manifest_path.exists():
        raise FileNotFoundError(f"TopologyBench manifest not found: {manifest_path}")
    return json.loads(manifest_path.read_text())


def md5sum(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_topologybench_zip(
    *,
    manifest_path: Path | None = None,
    zip_path: Path | None = None,
    no_download: bool = False,
    copy_into_data: bool = True,
    force_download: bool = False,
) -> Path:
    """Ensure TopologyBench zip exists in data/topologybench with correct checksum."""
    if force_download and no_download:
        raise RuntimeError("force_download requires network access (no_download is set).")
    repo_root = Path(__file__).resolve().parents[2]
    default_manifest = repo_root / "data" / "topologybench_manifest.json"
    manifest_path = manifest_path or Path(os.getenv("TOPBENCH_MANIFEST_PATH", default_manifest))
    manifest = read_manifest(manifest_path)

    data_dir = repo_root / "data" / "topologybench"
    data_dir.mkdir(parents=True, exist_ok=True)
    target_zip = data_dir / "real_topologies.zip"

    env_zip = os.getenv("TOPBENCH_ZIP_PATH")
    if env_zip:
        zip_path = Path(env_zip)

    if zip_path:
        if not zip_path.exists():
            raise FileNotFoundError(f"Provided TopologyBench zip not found: {zip_path}")
        if copy_into_data:
            if zip_path.resolve() != target_zip.resolve():
                shutil.copy2(zip_path, target_zip)
            zip_path = target_zip
        checksum = md5sum(zip_path)
        if checksum != manifest["md5"]:
            raise ValueError(f"TopologyBench md5 mismatch: expected {manifest['md5']} got {checksum}")
        return zip_path

    if force_download:
        target_zip.unlink(missing_ok=True)

    if target_zip.exists():
        checksum = md5sum(target_zip)
        if checksum != manifest["md5"]:
            if no_download:
                raise ValueError(
                    "TopologyBench zip checksum mismatch and downloads are disabled. "
                    "Place the correct zip at data/topologybench/real_topologies.zip "
                    f"(md5={manifest['md5']}) or enable network."
                )
            target_zip.unlink(missing_ok=True)
        else:
            return target_zip

    if no_download:
        raise RuntimeError(
            "TopologyBench zip missing. Run with --topologybench-zip PATH or enable network."
        )

    record_id = os.getenv("TOPBENCH_RECORD_ID", manifest["record_id"])
    filename = manifest["filename"]
    url = f"https://zenodo.org/records/{record_id}/files/{filename}?download=1"
    try:
        urllib.request.urlretrieve(url, target_zip)
    except Exception as exc:
        raise RuntimeError(
            "TopologyBench zip missing. Place it at data/topologybench/real_topologies.zip "
            f"and ensure md5={manifest['md5']}, or enable network."
        ) from exc
    checksum = md5sum(target_zip)
    if checksum != manifest["md5"]:
        target_zip.unlink(missing_ok=True)
        raise ValueError(
            "TopologyBench md5 mismatch after download. "
            f"Expected {manifest['md5']}."
        )
    return target_zip
