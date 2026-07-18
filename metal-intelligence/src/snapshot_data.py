#!/usr/bin/env python3
"""Save an immutable input snapshot and manifest for one pipeline run."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
REPORT_DIR = ROOT / "reports"
SNAPSHOT_DIR = ROOT / "data" / "snapshots"
CONFIG_PATH = ROOT / "config" / "metal_sources.json"
LATEST_POINTER = REPORT_DIR / "latest_snapshot.json"


SOURCE_FILES = [
    CONFIG_PATH,
    ROOT / "config" / "data_dictionary.json",
    RAW_DIR / "GC_F.csv",
    RAW_DIR / "SI_F.csv",
    RAW_DIR / "HG_F.csv",
    RAW_DIR / "USD_CNY.csv",
    RAW_DIR / "shfe_tin_contracts_daily.csv",
    PROCESSED_DIR / "metal_prices_daily.csv",
    PROCESSED_DIR / "usd_cny_daily.csv",
    PROCESSED_DIR / "shfe_tin_main_daily.csv",
    REPORT_DIR / "data_quality_report.json",
    REPORT_DIR / "usd_cny_quality_report.json",
    REPORT_DIR / "shfe_tin_quality_report.json",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative_to_root(path: Path) -> str:
    return str(path.relative_to(ROOT))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a source snapshot for one report run")
    parser.add_argument("--run-id", help="UTC run id, default: current timestamp")
    args = parser.parse_args(argv)

    captured_at = datetime.now(timezone.utc)
    run_id = args.run_id or captured_at.strftime("%Y%m%dT%H%M%SZ")
    snapshot_dir = SNAPSHOT_DIR / run_id
    if snapshot_dir.exists():
        raise FileExistsError(f"Snapshot already exists: {snapshot_dir}")
    snapshot_dir.mkdir(parents=True, exist_ok=False)

    missing = [path for path in SOURCE_FILES if not path.exists()]
    if missing:
        shutil.rmtree(snapshot_dir)
        raise FileNotFoundError("Missing snapshot inputs: " + ", ".join(relative_to_root(path) for path in missing))

    files = []
    for source_path in SOURCE_FILES:
        snapshot_path = snapshot_dir / source_path.relative_to(ROOT)
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, snapshot_path)
        files.append({
            "path": relative_to_root(source_path),
            "snapshot_path": str(snapshot_path.relative_to(snapshot_dir)),
            "bytes": snapshot_path.stat().st_size,
            "sha256": sha256(snapshot_path),
        })

    manifest = {
        "schema_version": "1.0",
        "run_id": run_id,
        "captured_at": captured_at.isoformat(),
        "source_config": json.loads(CONFIG_PATH.read_text(encoding="utf-8")),
        "files": files,
    }
    manifest_path = snapshot_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    pointer = {
        "run_id": run_id,
        "captured_at": manifest["captured_at"],
        "snapshot_dir": str(snapshot_dir.relative_to(ROOT)),
        "manifest": str(manifest_path.relative_to(ROOT)),
        "manifest_sha256": sha256(manifest_path),
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    LATEST_POINTER.write_text(json.dumps(pointer, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"run_id": run_id, "snapshot_dir": str(snapshot_dir), "file_count": len(files)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
