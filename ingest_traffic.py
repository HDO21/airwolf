#!/usr/bin/env python3
"""Ingest traffic detector data in live snapshot or CSV backfill mode.

live mode:
    Queries the ArcGIS MapServer for each study area BBOX, paginates if needed,
    and writes staging/traffic_live_<TIMESTAMP>.parquet.
    Also updates staging/traffic_detector_registry.parquet with known detectors.

backfill mode:
    Reads the historical CSV (ll_2025.csv format), computes derived flow fields,
    filters to detectors known from the registry, and writes
    staging/traffic_backfill_<filename>.parquet.

Usage:
    python ingest_traffic.py --mode live
    python ingest_traffic.py --mode backfill --file /path/to/ll_2025.csv
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from validate import validate

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)

_ARCGIS_BASE = (
    "https://tarktee.mnt.ee/tarktee/rest/services/traffic_detectors/MapServer/0"
)
_STAGING = Path("staging")
_TIMEOUT = 30
_MAX_RETRIES = 3
_BACKOFF = 5
_MAX_RECORD_COUNT = 1000

STUDY_AREAS: dict[str, dict[str, int]] = {
    "tallinn": {"x_min": 526818, "x_max": 557609, "y_min": 6580812, "y_max": 6601992},
    "narva":   {"x_min": 732765, "x_max": 739464, "y_min": 6585793, "y_max": 6591660},
    "tartu":   {"x_min": 643432, "x_max": 663197, "y_min": 6459800, "y_max": 6478907},
}

_LIVE_OUT_FIELDS = ",".join([
    "traffic_detector_id",
    "site_name",
    "road_name",
    "measurement_time",
    "total_flow_forwards",
    "total_flow_backwards",
    "heavy_traffic_forwards",
    "heavy_traffic_backwards",
    "average_speed_forwards",
    "average_speed_backwards",
    "relative_speed_forwards",
    "relative_speed_backwards",
])

# Vehicle class columns 1-10 used to compute total_flow
_VEHICLE_CLASS_COLS = [str(i) for i in range(1, 11)]
# Columns 6, 7, 8 = Rigid, Rigid+Trailer, Articulated HGV → heavy
_HEAVY_COLS = ["6", "7", "8"]


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _query_arcgis(params: dict[str, Any]) -> dict:
    url = f"{_ARCGIS_BASE}/query"
    defaults: dict[str, Any] = {
        "f": "json",
        "outSR": "3301",
        "returnGeometry": "true",
    }
    defaults.update(params)
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = requests.get(
                url,
                params=defaults,
                headers={"Accept": "application/json"},
                timeout=_TIMEOUT,
            )
            if resp.status_code >= 500:
                raise requests.HTTPError(response=resp)
            resp.raise_for_status()
            return resp.json()
        except (requests.HTTPError, requests.ConnectionError) as exc:
            if attempt == _MAX_RETRIES:
                raise
            log.warning("Attempt %d/%d failed: %s — retrying in %ds", attempt, _MAX_RETRIES, exc, _BACKOFF)
            time.sleep(_BACKOFF)
    return {}


# ---------------------------------------------------------------------------
# Live mode
# ---------------------------------------------------------------------------

def _fetch_area(area_name: str, bbox: dict[str, int]) -> list[dict]:
    geometry = f"{bbox['x_min']},{bbox['y_min']},{bbox['x_max']},{bbox['y_max']}"
    rows: list[dict] = []
    offset = 0
    while True:
        log.info("  %s: querying offset=%d ...", area_name, offset)
        result = _query_arcgis({
            "where": "1=1",
            "geometry": geometry,
            "geometryType": "esriGeometryEnvelope",
            "inSR": "3301",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": _LIVE_OUT_FIELDS,
            "resultOffset": offset,
            "resultRecordCount": _MAX_RECORD_COUNT,
        })
        features = result.get("features", [])
        for feat in features:
            attr = feat.get("attributes", {})
            geom = feat.get("geometry") or {}
            rows.append({
                "traffic_detector_id": attr.get("traffic_detector_id"),
                "site_name": attr.get("site_name"),
                "road_name": attr.get("road_name"),
                "measurement_time": attr.get("measurement_time"),
                "total_flow_forwards": attr.get("total_flow_forwards"),
                "total_flow_backwards": attr.get("total_flow_backwards"),
                "heavy_traffic_forwards": attr.get("heavy_traffic_forwards"),
                "heavy_traffic_backwards": attr.get("heavy_traffic_backwards"),
                "average_speed_forwards": attr.get("average_speed_forwards"),
                "average_speed_backwards": attr.get("average_speed_backwards"),
                "relative_speed_forwards": attr.get("relative_speed_forwards"),
                "relative_speed_backwards": attr.get("relative_speed_backwards"),
                "x_3301": geom.get("x"),
                "y_3301": geom.get("y"),
                "area": area_name,
            })
        if len(features) < _MAX_RECORD_COUNT:
            break
        offset += _MAX_RECORD_COUNT
    return rows


def ingest_live() -> None:
    _STAGING.mkdir(exist_ok=True)
    all_rows: list[dict] = []

    for area_name, bbox in STUDY_AREAS.items():
        log.info("Fetching detectors in %s ...", area_name)
        rows = _fetch_area(area_name, bbox)
        log.info("  %s: %d records", area_name, len(rows))
        all_rows.extend(rows)

    df = pd.DataFrame(all_rows)
    if not df.empty:
        df = df.drop_duplicates(subset=["traffic_detector_id"])
    log.info("Total unique detectors: %d", len(df))

    # Write live snapshot
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = _STAGING / f"traffic_live_{ts}.parquet"
    df.to_parquet(out_path, index=False)
    log.info("Written %d rows to %s", len(df), out_path)

    # Update detector registry (used by backfill to filter relevant rows)
    if not df.empty and "traffic_detector_id" in df.columns:
        registry_cols = ["traffic_detector_id", "site_name", "road_name", "x_3301", "y_3301", "area"]
        reg = df[[c for c in registry_cols if c in df.columns]].copy()
        registry_path = _STAGING / "traffic_detector_registry.parquet"
        if registry_path.exists():
            existing = pd.read_parquet(registry_path)
            reg = (
                pd.concat([existing, reg], ignore_index=True)
                .drop_duplicates(subset=["traffic_detector_id"])
            )
        reg.to_parquet(registry_path, index=False)
        log.info("Registry updated: %d detectors in %s", len(reg), registry_path)

    vr = validate(df, "traffic_live")
    log.info("Validation: passed=%s  issues=%d", vr["passed"], len(vr["issues"]))


# ---------------------------------------------------------------------------
# Backfill mode
# ---------------------------------------------------------------------------

def ingest_backfill(csv_path: Path) -> None:
    _STAGING.mkdir(exist_ok=True)

    log.info("Reading CSV: %s ...", csv_path)
    df = pd.read_csv(csv_path, dtype=str)
    log.info("Read %d rows from CSV", len(df))

    # Parse timestamp — format M/D/YY H:MM (e.g. "1/5/25 8:30")
    df["aeg"] = pd.to_datetime(df["aeg"], format="%m/%d/%y %H:%M", errors="coerce")
    bad_ts = int(df["aeg"].isna().sum())
    if bad_ts:
        log.warning("%d rows with unparseable 'aeg' timestamp", bad_ts)

    # Convert vehicle class columns to numeric
    vc_present = [c for c in _VEHICLE_CLASS_COLS if c in df.columns]
    heavy_present = [c for c in _HEAVY_COLS if c in df.columns]

    if vc_present:
        for col in vc_present:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        df["total_flow"] = df[vc_present].sum(axis=1)
    else:
        log.warning("No vehicle class columns (1-10) found; total_flow will be 0")
        df["total_flow"] = 0

    if heavy_present:
        for col in heavy_present:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        df["heavy_vehicle_count"] = df[heavy_present].sum(axis=1)
    else:
        log.warning("No heavy vehicle columns (6, 7, 8) found; heavy_vehicle_count will be 0")
        df["heavy_vehicle_count"] = 0

    mask = df["total_flow"] > 0
    df["heavy_vehicle_share"] = pd.NA
    df.loc[mask, "heavy_vehicle_share"] = (
        df.loc[mask, "heavy_vehicle_count"] / df.loc[mask, "total_flow"]
    )
    df["heavy_vehicle_share"] = pd.to_numeric(df["heavy_vehicle_share"], errors="coerce")

    # Filter to detectors known from the live registry
    registry_path = _STAGING / "traffic_detector_registry.parquet"
    if registry_path.exists():
        registry = pd.read_parquet(registry_path)
        known_ids = set(registry["traffic_detector_id"].dropna().astype(str))
        before = len(df)
        df = df[df["id"].astype(str).isin(known_ids)].copy()
        log.info(
            "Filtered to %d rows (from %d) matching %d known detector IDs",
            len(df), before, len(known_ids),
        )
    else:
        log.warning(
            "No detector registry at %s — loading all %d rows without spatial filter",
            registry_path, len(df),
        )

    vr = validate(df, "traffic_backfill")
    log.info("Validation: passed=%s  issues=%d", vr["passed"], len(vr["issues"]))

    out_path = _STAGING / f"traffic_backfill_{csv_path.stem}.parquet"
    df.to_parquet(out_path, index=False)
    log.info("Written %d rows to %s", len(df), out_path)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--mode", choices=["live", "backfill"], required=True,
                        help="live: fetch current snapshot  backfill: load historical CSV")
    parser.add_argument("--file", type=Path,
                        help="Path to the CSV file (required for --mode backfill)")
    args = parser.parse_args()

    if args.mode == "live":
        ingest_live()
    else:
        if not args.file:
            parser.error("--file <path> is required for --mode backfill")
        if not args.file.exists():
            log.error("File not found: %s", args.file)
            sys.exit(1)
        ingest_backfill(args.file)


if __name__ == "__main__":
    main()
