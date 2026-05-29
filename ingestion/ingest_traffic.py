#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from pyproj import Transformer

from ingestion.db import get_conn, insert_pipeline_run, upsert_rows

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

ARCGIS_BASE = "https://tarktee.mnt.ee/tarktee/rest/services/traffic_detectors/MapServer/0"
TIMEOUT = 30
MAX_RETRIES = 3
BACKOFF = 5
MAX_RECORDS = 1000

STUDY_AREAS: dict[str, dict[str, int]] = {
    "tallinn": {"x_min": 526818, "x_max": 557609, "y_min": 6580812, "y_max": 6601992},
    "narva": {"x_min": 732765, "x_max": 739464, "y_min": 6585793, "y_max": 6591660},
    "tartu": {"x_min": 643432, "x_max": 663197, "y_min": 6459800, "y_max": 6478907},
}

LIVE_FIELDS = ",".join([
    "traffic_detector_id", "site_name", "road_name", "measurement_time",
    "total_flow_forwards", "total_flow_backwards",
    "heavy_traffic_forwards", "heavy_traffic_backwards",
    "average_speed_forwards", "average_speed_backwards",
    "relative_speed_forwards", "relative_speed_backwards",
])

wgs84_to_3301 = Transformer.from_crs("EPSG:4326", "EPSG:3301", always_xy=True)
_3301_to_wgs84 = Transformer.from_crs("EPSG:3301", "EPSG:4326", always_xy=True)


def _query_arcgis(params: dict[str, Any]) -> dict[str, Any]:
    url = f"{ARCGIS_BASE}/query"
    base = {"f": "json", "outSR": "3301", "returnGeometry": "true"}
    base.update(params)
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, params=base, headers={"Accept": "application/json"}, timeout=TIMEOUT)
            if resp.status_code >= 500:
                raise requests.HTTPError(response=resp)
            resp.raise_for_status()
            return resp.json()
        except (requests.HTTPError, requests.ConnectionError, requests.Timeout) as exc:
            if attempt == MAX_RETRIES:
                raise
            log.warning("Attempt %d/%d failed: %s — retrying in %ds", attempt, MAX_RETRIES, exc, BACKOFF)
            time.sleep(BACKOFF)
    return {}


def _run_id(prefix: str) -> str:
    return f"{prefix}_{dt.datetime.now(dt.UTC).strftime('%Y%m%dT%H%M%SZ')}"


def _none_if_nan(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def _load_stations_from_excel(xlsx_path: Path) -> list[dict[str, Any]]:
    df = pd.read_excel(xlsx_path)
    df = df.dropna(subset=["ID", "Lat", "Lon"]).copy()
    df["ID"] = df["ID"].astype(str).str.strip()
    df["Lat"] = pd.to_numeric(df["Lat"], errors="coerce")
    df["Lon"] = pd.to_numeric(df["Lon"], errors="coerce")
    df = df.dropna(subset=["Lat", "Lon"])

    xs, ys = wgs84_to_3301.transform(df["Lon"].to_numpy(), df["Lat"].to_numpy())
    df["x_3301"] = xs
    df["y_3301"] = ys

    def area(row: pd.Series) -> str | None:
        for name, bb in STUDY_AREAS.items():
            if bb["x_min"] <= row["x_3301"] <= bb["x_max"] and bb["y_min"] <= row["y_3301"] <= bb["y_max"]:
                return name
        return None

    df["area"] = df.apply(area, axis=1)
    df = df[df["area"].notna()].copy()
    road_col = "Tee nimi" if "Tee nimi" in df.columns else None
    rows = []
    for _, r in df.iterrows():
        rows.append({
            "traffic_detector_id": str(r["ID"]),
            "site_name": _none_if_nan(r.get("Nimetus")),
            "road_name": _none_if_nan(r.get(road_col)) if road_col else None,
            "area": r["area"],
            "lat": float(r["Lat"]),
            "lon": float(r["Lon"]),
            "x_3301": float(r["x_3301"]),
            "y_3301": float(r["y_3301"]),
            "payload": {k: _none_if_nan(v) for k, v in r.to_dict().items()},
        })
    return rows


def _upsert_registry(rows: list[dict[str, Any]], run_id: str) -> int:
    if not rows:
        return 0
    prepared = []
    for r in rows:
        prepared.append({
            "traffic_detector_id": str(r.get("traffic_detector_id")),
            "site_name": r.get("site_name"),
            "road_name": r.get("road_name"),
            "area": r.get("area"),
            "lat": r.get("lat"),
            "lon": r.get("lon"),
            "x_3301": r.get("x_3301"),
            "y_3301": r.get("y_3301"),
            "payload": r.get("payload", r),
            "run_id": run_id,
        })
    with get_conn() as conn:
        return upsert_rows(
            conn,
            "staging.traffic_detector_registry_raw",
            prepared,
            ["traffic_detector_id", "site_name", "road_name", "area", "lat", "lon", "x_3301", "y_3301", "payload", "run_id"],
            ["traffic_detector_id"],
        )


def ingest_live() -> int:
    run_id = _run_id("traffic_live")
    all_rows: list[dict[str, Any]] = []
    registry_rows: list[dict[str, Any]] = []

    for area_name, bbox in STUDY_AREAS.items():
        geometry = f"{bbox['x_min']},{bbox['y_min']},{bbox['x_max']},{bbox['y_max']}"
        offset = 0
        while True:
            result = _query_arcgis({
                "where": "1=1",
                "geometry": geometry,
                "geometryType": "esriGeometryEnvelope",
                "inSR": "3301",
                "spatialRel": "esriSpatialRelIntersects",
                "outFields": LIVE_FIELDS,
                "resultOffset": offset,
                "resultRecordCount": MAX_RECORDS,
            })
            features = result.get("features", [])
            for feat in features:
                attr = feat.get("attributes", {}) or {}
                geom = feat.get("geometry") or {}
                raw = dict(attr)
                raw["x_3301"] = geom.get("x")
                raw["y_3301"] = geom.get("y")
                raw["area"] = area_name
                row = {
                    "traffic_detector_id": str(raw.get("traffic_detector_id")),
                    "measurement_time": raw.get("measurement_time"),
                    "area": area_name,
                    "site_name": raw.get("site_name"),
                    "road_name": raw.get("road_name"),
                    "x_3301": raw.get("x_3301"),
                    "y_3301": raw.get("y_3301"),
                    "payload": raw,
                    "run_id": run_id,
                }
                all_rows.append(row)

                if raw.get("traffic_detector_id") is not None:
                    reg = {
                        "traffic_detector_id": str(raw.get("traffic_detector_id")),
                        "site_name": raw.get("site_name"),
                        "road_name": raw.get("road_name"),
                        "area": area_name,
                        "x_3301": raw.get("x_3301"),
                        "y_3301": raw.get("y_3301"),
                        "payload": raw,
                    }
                    if raw.get("x_3301") is not None and raw.get("y_3301") is not None:
                        lon, lat = _3301_to_wgs84.transform(raw["x_3301"], raw["y_3301"])
                        reg["lon"] = lon
                        reg["lat"] = lat
                    registry_rows.append(reg)
            if len(features) < MAX_RECORDS:
                break
            offset += MAX_RECORDS

    with get_conn() as conn:
        insert_pipeline_run(conn, run_id, "traffic_live", "running")
        count = upsert_rows(
            conn,
            "staging.traffic_live_raw",
            all_rows,
            ["traffic_detector_id", "measurement_time", "area", "site_name", "road_name", "x_3301", "y_3301", "payload", "run_id"],
            ["traffic_detector_id", "measurement_time", "area"],
        )
        insert_pipeline_run(conn, run_id, "traffic_live", "success", f"Loaded {count} rows")
    _upsert_registry(registry_rows, run_id)
    return count


def ingest_backfill(csv_path: Path, stations_file: Path | None = None) -> int:
    run_id = _run_id("traffic_backfill")
    if stations_file is not None:
        registry = _load_stations_from_excel(stations_file)
        _upsert_registry(registry, run_id)

    df = pd.read_csv(csv_path, dtype=str)
    if "aeg" not in df.columns or "id" not in df.columns or "kanal" not in df.columns:
        raise ValueError("Traffic backfill CSV must contain id, kanal and aeg columns")
    parsed_aeg = pd.to_datetime(df["aeg"], format="%Y-%m-%d %H:%M:%S", errors="coerce")
    df["aeg"] = parsed_aeg.where(parsed_aeg.notna(), pd.to_datetime(df["aeg"], errors="coerce"))

    rows = []
    for _, r in df.iterrows():
        raw = {k: _none_if_nan(v) for k, v in r.to_dict().items()}
        rows.append({
            "id": raw.get("id"),
            "kanal": raw.get("kanal"),
            "aeg": raw.get("aeg"),
            "payload": raw,
            "run_id": run_id,
        })

    with get_conn() as conn:
        insert_pipeline_run(conn, run_id, "traffic_backfill", "running")
        count = upsert_rows(
            conn,
            "staging.traffic_backfill_raw",
            rows,
            ["id", "kanal", "aeg", "payload", "run_id"],
            ["id", "kanal", "aeg"],
        )
        insert_pipeline_run(conn, run_id, "traffic_backfill", "success", f"Loaded {count} rows")
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Load traffic raw data into PostgreSQL staging tables")
    parser.add_argument("--mode", choices=["live", "backfill"], required=True)
    parser.add_argument("--file", type=Path, help="CSV path, required for --mode backfill")
    parser.add_argument("--stations-file", type=Path, help="Excel file with detector IDs and coordinates")
    args = parser.parse_args()

    if args.mode == "live":
        ingest_live()
        return
    if not args.file:
        parser.error("--file <path> is required for --mode backfill")
    if not args.file.exists():
        log.error("File not found: %s", args.file)
        sys.exit(1)
    if args.stations_file and not args.stations_file.exists():
        log.error("Stations file not found: %s", args.stations_file)
        sys.exit(1)
    ingest_backfill(args.file, args.stations_file)


if __name__ == "__main__":
    main()
