#!/usr/bin/env python3
"""Main orchestration script — runs the full medallion pipeline.

Steps:
    1. Ingest  — fetch raw data from APIs into data/staging/ (never overwrite)
    2. Transform — normalise staging → data/intermediate/
    3. Mart    — build dashboard-ready tables in data/mart/
    4. Stamp   — write data/staging/_last_updated.txt for the dashboard

Reads TRAFFIC_BACKFILL_CSV and TRAFFIC_STATIONS_FILE from .env.

Usage:
    python run_pipeline.py
    python run_pipeline.py --year-start 2024 --month-start 1 --year-end 2025 --month-end 12
"""
from __future__ import annotations

import argparse
import datetime
import logging
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)

_HERE    = Path(__file__).parent
_STAGING = _HERE / "data" / "staging"
_PYTHON  = sys.executable


def _run(label: str, cmd: list[str]) -> bool:
    log.info("=== %s ===", label)
    result = subprocess.run([_PYTHON] + cmd, cwd=_HERE)
    if result.returncode != 0:
        log.error("%s FAILED (exit %d)", label, result.returncode)
        return False
    log.info("%s OK", label)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    now = datetime.datetime.now()
    parser.add_argument("--year-start",  type=int, default=2024)
    parser.add_argument("--month-start", type=int, default=1)
    parser.add_argument("--year-end",    type=int, default=now.year)
    parser.add_argument("--month-end",   type=int, default=now.month)
    args = parser.parse_args()

    backfill_csv   = os.getenv("TRAFFIC_BACKFILL_CSV", "")
    stations_file  = os.getenv("TRAFFIC_STATIONS_FILE", "")

    _STAGING.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    # ── 1. INGEST ──────────────────────────────────────────────────────────
    # Weather: full configured range so the dashboard period is always covered
    label = (f"Ingest weather {args.year_start}-{args.month_start:02d} → "
             f"{args.year_end}-{args.month_end:02d}")
    if not _run(label, [
        "ingest_weather.py",
        str(args.year_start), str(args.month_start),
        str(args.year_end),   str(args.month_end),
    ]):
        failures.append(label)

    # Air quality: full configured range
    label = (f"Ingest AQ {args.year_start}-{args.month_start:02d} → "
             f"{args.year_end}-{args.month_end:02d}")
    if not _run(label, [
        "ingest_air_quality.py",
        str(args.year_start), str(args.month_start),
        str(args.year_end),   str(args.month_end),
    ]):
        failures.append(label)

    # Traffic live snapshot (updates detector registry)
    if not _run("Ingest traffic live", ["ingest_traffic.py", "--mode", "live"]):
        failures.append("Ingest traffic live")

    # Traffic backfill (if CSV is configured)
    if backfill_csv and Path(backfill_csv).exists():
        cmd = ["ingest_traffic.py", "--mode", "backfill", "--file", backfill_csv]
        if stations_file and Path(stations_file).exists():
            cmd += ["--stations-file", stations_file]
        if not _run("Ingest traffic backfill", cmd):
            failures.append("Ingest traffic backfill")
    else:
        log.warning("Traffic backfill skipped — set TRAFFIC_BACKFILL_CSV in .env")

    # ── 2. TRANSFORM ──────────────────────────────────────────────────────
    transform_cmd = [
        "run_transform.py",
        "--year-start",  str(args.year_start),
        "--month-start", str(args.month_start),
        "--year-end",    str(args.year_end),
        "--month-end",   str(args.month_end),
    ]
    if not _run("Transform staging → intermediate", transform_cmd):
        failures.append("Transform")

    # ── 3. MART ───────────────────────────────────────────────────────────
    if not _run("Build mart", ["run_mart.py"]):
        failures.append("Build mart")

    # ── 4. STAMP ──────────────────────────────────────────────────────────
    marker = _STAGING / "_last_updated.txt"
    marker.write_text(datetime.datetime.now().isoformat())
    log.info("Last-updated marker: %s", marker)

    if failures:
        log.error("Pipeline finished with %d failure(s): %s", len(failures), failures)
        sys.exit(1)
    else:
        log.info("Pipeline finished successfully.")


if __name__ == "__main__":
    main()
