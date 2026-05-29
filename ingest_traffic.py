#!/usr/bin/env python3
"""Ingest raw traffic detector data into data/staging/.

Preserves source data with minimal modification. All transformation,
lane aggregation, spatial filtering and validation are done by run_transform.py.

live mode   — Fetches current ArcGIS snapshot; stores timestamped raw parquet
              and updates the detector registry used by transform.
backfill    — Reads historical CSV; upserts raw lane-level rows into
              traffic_backfill.parquet (deduplicated on id × kanal × aeg).

Usage:
    python ingest_traffic.py --mode live
    python ingest_traffic.py --mode backfill --file /path/to/ll_2025.csv \\
        [--stations-file "/path/to/LL jaamad.xlsx"]
"""
from __future__ import annotations

import argparse
import datetime
import logging
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from pyproj import Transformer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)

_ARCGIS_BASE = (
    "https://tarktee.mnt.ee/tarktee/rest/services/traffic_detectors/MapServer/0"
)
_STAGING      = Path("data/staging")
_TIMEOUT      = 30
_MAX_RETRIES  = 3
_BACKOFF      = 5
_MAX_RECORDS  = 1000

STUDY_AREAS: dict[str, dict[str, int]] = {
    "tallinn": {"x_min": 526818, "x_max": 557609, "y_min": 6580812, "y_max": 6601992},
    "narva":   {"x_min": 732765, "x_max": 739464, "y_min": 6585793, "y_max": 6591660},
    "tartu":   {"x_min": 643432, "x_max": 663197, "y_min": 6459800, "y_max": 6478907},
}

_LIVE_FIELDS = ",".join([
    "traffic_detector_id", "site_name", "road_name", "measurement_time",
    "total_flow_forwards", "total_flow_backwards",
    "heavy_traffic_forwards", "heavy_traffic_backwards",
    "average_speed_forwards", "average_speed_backwards",
    "relative_speed_forwards", "relative_speed_backwards",
])
_VEHICLE_COLS = [str(i) for i in range(1, 11)]
_HEAVY_COLS   = ["6", "7", "8"]

_wgs84_to_3301 = Transformer.from_crs("EPSG:4326", "EPSG:3301", always_xy=True)
_3301_to_wgs84 = Transformer.from_crs("EPSG:3301", "EPSG:4326", always_xy=True)


def _query_arcgis(params: dict[str, Any]) -> dict:
    url = f"{_ARCGIS_BASE}/query"
    base = {"f": "json", "outSR": "3301", "returnGeometry": "true"}
    base.update(params)
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = requests.get(url, params=base,
                                headers={"Accept": "application/json"}, timeout=_TIMEOUT)
            if resp.status_code >= 500:
                raise requests.HTTPError(response=resp)
            resp.raise_for_status()
            return resp.json()
        except (requests.HTTPError, requests.ConnectionError) as exc:
            if attempt == _MAX_RETRIES:
                raise
            log.warning("Attempt %d/%d failed: %s — retrying in %ds",
                        attempt, _MAX_RETRIES, exc, _BACKOFF)
            time.sleep(_BACKOFF)
    return {}


def _upsert_parquet(path: Path, new_df: pd.DataFrame, pk: list[str]) -> None:
    if path.exists():
        existing = pd.read_parquet(path)
        combined = (
            pd.concat([existing, new_df], ignore_index=True)
            .drop_duplicates(subset=pk, keep="last")
        )
    else:
        combined = new_df
    combined.to_parquet(path, index=False)
    log.info("Written %d rows to %s", len(combined), path)


# ---------------------------------------------------------------------------
# Station registry
# ---------------------------------------------------------------------------

def _load_stations_from_excel(xlsx_path: Path) -> pd.DataFrame:
    """Read 'LL jaamad.xlsx', project to EPSG:3301, filter to study areas.
    Returns columns: traffic_detector_id, site_name, road_name, area, lat, lon, x_3301, y_3301
    """
    df = pd.read_excel(xlsx_path)
    df = df.dropna(subset=["ID", "Lat", "Lon"]).copy()
    df["ID"]  = df["ID"].astype(str).str.strip()
    df["Lat"] = pd.to_numeric(df["Lat"], errors="coerce")
    df["Lon"] = pd.to_numeric(df["Lon"], errors="coerce")
    df = df.dropna(subset=["Lat", "Lon"])

    xs, ys = _wgs84_to_3301.transform(df["Lon"].to_numpy(), df["Lat"].to_numpy())
    df["x_3301"] = xs
    df["y_3301"] = ys

    def _area(row: pd.Series) -> str | None:
        for name, bb in STUDY_AREAS.items():
            if bb["x_min"] <= row["x_3301"] <= bb["x_max"] and \
               bb["y_min"] <= row["y_3301"] <= bb["y_max"]:
                return name
        return None

    df["area"] = df.apply(_area, axis=1)
    df = df[df["area"].notna()].copy()
    road_col = "Tee nimi" if "Tee nimi" in df.columns else None
    return df.rename(columns={"ID": "traffic_detector_id", "Nimetus": "site_name"}).assign(
        road_name=df[road_col] if road_col else None,
        lat=df["Lat"],
        lon=df["Lon"],
    )[["traffic_detector_id", "site_name", "road_name", "area",
       "lat", "lon", "x_3301", "y_3301"]].reset_index(drop=True)


def _update_registry(new_rows: pd.DataFrame) -> None:
    registry_path = _STAGING / "traffic_detector_registry.parquet"
    if registry_path.exists():
        existing = pd.read_parquet(registry_path)
        combined = (
            pd.concat([existing, new_rows], ignore_index=True)
            .drop_duplicates(subset=["traffic_detector_id"], keep="last")
        )
    else:
        combined = new_rows
    combined.to_parquet(registry_path, index=False)
    log.info("Registry: %d detectors in %s", len(combined), registry_path)


# ---------------------------------------------------------------------------
# Live mode — raw snapshot
# ---------------------------------------------------------------------------

def ingest_live() -> None:
    _STAGING.mkdir(parents=True, exist_ok=True)
    ingested_at = datetime.datetime.now(datetime.timezone.utc)
    run_id = ingested_at.strftime("%Y%m%dT%H%M%SZ")
    all_rows: list[dict] = []

    for area_name, bbox in STUDY_AREAS.items():
        geometry = f"{bbox['x_min']},{bbox['y_min']},{bbox['x_max']},{bbox['y_max']}"
        offset = 0
        while True:
            log.info("  %s offset=%d ...", area_name, offset)
            result = _query_arcgis({
                "where": "1=1",
                "geometry": geometry,
                "geometryType": "esriGeometryEnvelope",
                "inSR": "3301",
                "spatialRel": "esriSpatialRelIntersects",
                "outFields": _LIVE_FIELDS,
                "resultOffset": offset,
                "resultRecordCount": _MAX_RECORDS,
            })
            features = result.get("features", [])
            for feat in features:
                attr = feat.get("attributes", {})
                geom = feat.get("geometry") or {}
                row  = dict(attr)
                row["x_3301"] = geom.get("x")
                row["y_3301"] = geom.get("y")
                row["area"]   = area_name
                all_rows.append(row)
            if len(features) < _MAX_RECORDS:
                break
            offset += _MAX_RECORDS

    df = pd.DataFrame(all_rows)
    df["_ingested_at"] = ingested_at.isoformat()
    df["_run_id"]      = run_id
    log.info("Live snapshot: %d records", len(df))

    # Write raw snapshot (new file each run — live data is a point-in-time snapshot)
    path = _STAGING / f"traffic_live_{run_id}.parquet"
    df.to_parquet(path, index=False)
    log.info("Written %s", path)

    # Update registry with lat/lon from 3301
    if not df.empty and "traffic_detector_id" in df.columns:
        reg = df[["traffic_detector_id", "site_name", "road_name",
                  "x_3301", "y_3301", "area"]].drop_duplicates(
            subset=["traffic_detector_id"]
        ).copy()
        valid = reg["x_3301"].notna() & reg["y_3301"].notna()
        if valid.any():
            lons, lats = _3301_to_wgs84.transform(
                reg.loc[valid, "x_3301"].to_numpy(),
                reg.loc[valid, "y_3301"].to_numpy(),
            )
            reg.loc[valid, "lon"] = lons
            reg.loc[valid, "lat"] = lats
        _update_registry(reg)


# ---------------------------------------------------------------------------
# Backfill mode — raw CSV rows
# ---------------------------------------------------------------------------

def ingest_backfill(csv_path: Path, stations_file: Path | None = None) -> None:
    _STAGING.mkdir(parents=True, exist_ok=True)
    ingested_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    if stations_file is not None:
        log.info("Updating registry from %s ...", stations_file)
        excel_stations = _load_stations_from_excel(stations_file)
        log.info("  Found %d study-area stations: %s",
                 len(excel_stations),
                 excel_stations.groupby("area")["traffic_detector_id"].count().to_dict())
        _update_registry(excel_stations)

    log.info("Reading CSV: %s ...", csv_path)
    df = pd.read_csv(csv_path, dtype=str)
    log.info("Read %d rows", len(df))

    df["_ingested_at"] = ingested_at
    df["aeg"] = pd.to_datetime(df["aeg"], format="%Y-%m-%d %H:%M:%S", errors="coerce")
    bad = int(df["aeg"].isna().sum())
    if bad:
        mask = df["aeg"].isna()
        df.loc[mask, "aeg"] = pd.to_datetime(df.loc[mask, "aeg"].astype(str), errors="coerce")
    if bad := int(df["aeg"].isna().sum()):
        log.warning("%d rows with unparseable 'aeg'", bad)

    # Upsert by primary key — preserves full lane-level raw data
    _upsert_parquet(
        _STAGING / "traffic_backfill.parquet",
        df,
        pk=["id", "kanal", "aeg"],
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", choices=["live", "backfill"], required=True)
    parser.add_argument("--file", type=Path,
                        help="CSV path (required for --mode backfill)")
    parser.add_argument("--stations-file", type=Path, dest="stations_file",
                        help="Excel file with detector IDs and coordinates")
    args = parser.parse_args()

    if args.mode == "live":
        ingest_live()
    else:
        if not args.file:
            parser.error("--file <path> is required for --mode backfill")
        if not args.file.exists():
            log.error("File not found: %s", args.file)
            sys.exit(1)
        if args.stations_file and not args.stations_file.exists():
            log.error("Stations file not found: %s", args.stations_file)
            sys.exit(1)
        ingest_backfill(args.file, stations_file=args.stations_file)


if __name__ == "__main__":
    main()
