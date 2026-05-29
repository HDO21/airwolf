#!/usr/bin/env python3
"""Transform staging raw data into normalised intermediate tables.

Reads from data/staging/, normalises each source, runs validation, and writes
standardised parquet files to data/intermediate/.

Intermediate files are rebuilt from staging on every run (idempotent).

Usage:
    python run_transform.py                              # all months in staging
    python run_transform.py --year-start 2025 --month-start 12   # specific range
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd
from pyproj import Transformer

from validate import validate

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)

_STAGING      = Path("data/staging")
_INTERMEDIATE = Path("data/intermediate")

# ─── Weather ─────────────────────────────────────────────────────────────────

_WEATHER_STATION_AREA = {
    "AJHARK01": "tallinn",
    "AJTART01": "tartu",
    "AJNARV01": "narva",
}
_ELEMENT_TO_COL = {
    "TA":    "temperature_c",
    "WS10M": "wind_speed_ms",
    "WD10M": "wind_direction_deg",
    "PR1H":  "precip_mm",
}


def _transform_weather(year: int, month: int) -> None:
    raw_path = _STAGING / f"weather_raw_{year}_{month:02d}.parquet"
    if not raw_path.exists():
        log.warning("Missing staging file: %s", raw_path)
        return

    raw = pd.read_parquet(raw_path)
    log.info("Weather %d-%02d: %d raw rows", year, month, len(raw))

    # Station coordinates
    stations_path = _STAGING / "weather_stations.parquet"
    coords: dict[str, dict] = {}
    if stations_path.exists():
        st = pd.read_parquet(stations_path).drop_duplicates(subset=["jaam_kood"])
        for _, row in st.iterrows():
            jk = row.get("jaam_kood")
            if jk and pd.notna(row.get("laiuskraad")) and pd.notna(row.get("pikkuskraad")):
                coords[jk] = {"lat": float(row["laiuskraad"]),
                               "lon": float(row["pikkuskraad"])}

    raw["obs_time"] = pd.to_datetime(
        raw["aasta"].astype(str) + "-"
        + raw["kuu"].astype(str).str.zfill(2) + "-"
        + raw["paev"].astype(str).str.zfill(2) + " "
        + raw["tund"].astype(str).str.zfill(2) + ":00:00",
        errors="coerce",
    )
    raw["col"] = raw["element_kood"].map(_ELEMENT_TO_COL)
    raw = raw.dropna(subset=["col", "obs_time"])
    raw["vaartus"] = pd.to_numeric(raw["vaartus"], errors="coerce")

    pivoted = raw.pivot_table(
        index=["jaam_kood", "obs_time"],
        columns="col", values="vaartus", aggfunc="first",
    ).reset_index()
    pivoted.columns.name = None

    if "jaam_nimi" in raw.columns:
        name_map = raw.groupby("jaam_kood")["jaam_nimi"].first()
        pivoted["station_name"] = pivoted["jaam_kood"].map(name_map).fillna(pivoted["jaam_kood"])
    else:
        pivoted["station_name"] = pivoted["jaam_kood"]

    for col in ["temperature_c", "wind_speed_ms", "wind_direction_deg", "precip_mm"]:
        if col not in pivoted.columns:
            pivoted[col] = float("nan")

    pivoted["area"] = pivoted["jaam_kood"].map(_WEATHER_STATION_AREA)
    pivoted["lat"]  = pivoted["jaam_kood"].map(lambda k: coords.get(k, {}).get("lat"))
    pivoted["lon"]  = pivoted["jaam_kood"].map(lambda k: coords.get(k, {}).get("lon"))

    out = pivoted.rename(columns={"jaam_kood": "station_id"})[
        ["station_id", "station_name", "area", "obs_time",
         "lat", "lon", "temperature_c", "wind_speed_ms", "wind_direction_deg", "precip_mm"]
    ]

    vr = validate(out, "weather")
    log.info("  Validation: passed=%s  issues=%d", vr["passed"], len(vr["issues"]))

    out_path = _INTERMEDIATE / f"weather_{year}_{month:02d}.parquet"
    out.to_parquet(out_path, index=False)
    log.info("  Written %d rows → %s", len(out), out_path)


# ─── Air quality ─────────────────────────────────────────────────────────────

_INDICATOR_MAP: dict[int, str] = {1: "SO2", 3: "NO2", 6: "O3", 21: "PM10", 23: "PM25"}

_AQ_STATION_META: dict[int, dict] = {
    4: {"name": "Narva",     "area": "narva",   "lat": 59.3722, "lon": 28.2007},
    5: {"name": "Liivalaia", "area": "tallinn", "lat": 59.4310, "lon": 24.7605},
    7: {"name": "Õismäe",   "area": "tallinn", "lat": 59.4140, "lon": 24.6497},
    8: {"name": "Tartu",     "area": "tartu",   "lat": 58.3706, "lon": 26.7348},
}


def _transform_aq(year: int, month: int) -> None:
    raw_path = _STAGING / f"air_quality_raw_{year}_{month:02d}.parquet"
    if not raw_path.exists():
        log.warning("Missing staging file: %s", raw_path)
        return

    raw = pd.read_parquet(raw_path)
    log.info("AQ %d-%02d: %d raw rows", year, month, len(raw))

    raw["obs_time"]  = pd.to_datetime(raw["measured"], errors="coerce")
    raw["value"]     = pd.to_numeric(raw["value"], errors="coerce")
    raw["pollutant"] = raw["indicator"].map(_INDICATOR_MAP)
    raw = raw.dropna(subset=["pollutant", "obs_time"])

    pivoted = raw.pivot_table(
        index=["station", "obs_time"],
        columns="pollutant", values="value", aggfunc="mean",
    ).reset_index()
    pivoted.columns.name = None

    for col in ["SO2", "O3", "NO2", "PM10", "PM25"]:
        if col not in pivoted.columns:
            pivoted[col] = float("nan")

    pivoted["station_name"] = pivoted["station"].map(
        lambda s: _AQ_STATION_META.get(s, {}).get("name", str(s))
    )
    pivoted["area"] = pivoted["station"].map(lambda s: _AQ_STATION_META.get(s, {}).get("area"))
    pivoted["lat"]  = pivoted["station"].map(lambda s: _AQ_STATION_META.get(s, {}).get("lat"))
    pivoted["lon"]  = pivoted["station"].map(lambda s: _AQ_STATION_META.get(s, {}).get("lon"))

    out = pivoted.rename(columns={"station": "station_id"})[
        ["station_id", "station_name", "area", "obs_time",
         "lat", "lon", "SO2", "O3", "NO2", "PM10", "PM25"]
    ]

    vr = validate(out, "air_quality")
    log.info("  Validation: passed=%s  issues=%d", vr["passed"], len(vr["issues"]))

    out_path = _INTERMEDIATE / f"air_quality_{year}_{month:02d}.parquet"
    out.to_parquet(out_path, index=False)
    log.info("  Written %d rows → %s", len(out), out_path)


# ─── Traffic ─────────────────────────────────────────────────────────────────

_EXCLUDED_DETECTOR_IDS: set[str] = {"944ab"}  # Ülenurme
_VEHICLE_COLS = [str(i) for i in range(1, 11)]
_HEAVY_COLS   = ["6", "7", "8"]


def _transform_traffic() -> None:
    raw_path      = _STAGING / "traffic_backfill.parquet"
    registry_path = _STAGING / "traffic_detector_registry.parquet"

    if not raw_path.exists():
        log.warning("Missing staging file: %s", raw_path)
        return
    if not registry_path.exists():
        log.warning("Registry not found — run ingest_traffic.py --mode backfill --stations-file ...")
        return

    raw = pd.read_parquet(raw_path)
    log.info("Traffic backfill: %d raw rows", len(raw))

    registry = pd.read_parquet(registry_path)
    known_ids = set(registry["traffic_detector_id"].dropna().astype(str))
    known_ids -= _EXCLUDED_DETECTOR_IDS

    raw = raw[raw["id"].astype(str).isin(known_ids)].copy()
    raw = raw[~raw["id"].astype(str).isin(_EXCLUDED_DETECTOR_IDS)].copy()
    log.info("  After filtering: %d rows (%d detectors)", len(raw), raw["id"].nunique())

    raw["aeg"] = pd.to_datetime(raw["aeg"], errors="coerce")
    raw = raw.dropna(subset=["aeg"])

    vc_present    = [c for c in _VEHICLE_COLS if c in raw.columns]
    heavy_present = [c for c in _HEAVY_COLS   if c in raw.columns]
    for col in vc_present + heavy_present:
        raw[col] = pd.to_numeric(raw[col], errors="coerce").fillna(0)

    raw["total_flow"]          = raw[vc_present].sum(axis=1) if vc_present else 0
    raw["heavy_vehicle_count"] = raw[heavy_present].sum(axis=1) if heavy_present else 0

    # Aggregate across lanes (kanal) → one row per (detector, hour)
    reg_lookup = registry.set_index("traffic_detector_id")[
        ["area", "site_name"]
    ].to_dict("index")

    agg = raw.groupby(["id", "aeg"], as_index=False).agg(
        total_flow=("total_flow", "sum"),
        heavy_vehicle_count=("heavy_vehicle_count", "sum"),
    )
    agg["heavy_vehicle_share"] = (
        agg["heavy_vehicle_count"] / agg["total_flow"]
    ).where(agg["total_flow"] > 0)

    agg["area"]      = agg["id"].astype(str).map(lambda i: reg_lookup.get(i, {}).get("area"))
    agg["site_name"] = agg["id"].astype(str).map(
        lambda i: reg_lookup.get(i, {}).get("site_name", i)
    )

    out = agg.rename(columns={"id": "detector_id", "aeg": "obs_time"})[
        ["detector_id", "site_name", "area", "obs_time",
         "total_flow", "heavy_vehicle_count", "heavy_vehicle_share"]
    ]
    out["heavy_vehicle_share"] = pd.to_numeric(out["heavy_vehicle_share"], errors="coerce")

    vr = validate(out, "traffic_backfill")
    log.info("  Validation: passed=%s  issues=%d", vr["passed"], len(vr["issues"]))

    out_path = _INTERMEDIATE / "traffic.parquet"
    out.to_parquet(out_path, index=False)
    log.info("  Written %d rows → %s", len(out), out_path)


# ─── CLI ─────────────────────────────────────────────────────────────────────

def _discover_months() -> list[tuple[int, int]]:
    """Return (year, month) pairs found in staging, from weather and AQ files."""
    months: set[tuple[int, int]] = set()
    for pattern in ("weather_raw_*.parquet", "air_quality_raw_*.parquet"):
        for f in _STAGING.glob(pattern):
            parts = f.stem.split("_")
            try:
                months.add((int(parts[-2]), int(parts[-1])))
            except (IndexError, ValueError):
                pass
    return sorted(months)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--year-start",  type=int, default=None)
    parser.add_argument("--month-start", type=int, default=None)
    parser.add_argument("--year-end",    type=int, default=None)
    parser.add_argument("--month-end",   type=int, default=None)
    args = parser.parse_args()

    _INTERMEDIATE.mkdir(parents=True, exist_ok=True)

    all_months = _discover_months()
    if not all_months:
        log.warning("No staging files found in %s", _STAGING)
        return

    if args.year_start and args.month_start:
        start = (args.year_start, args.month_start)
        end   = (args.year_end   or 9999, args.month_end or 12)
        months = [(y, m) for y, m in all_months if start <= (y, m) <= end]
    else:
        months = all_months

    log.info("Transforming %d month(s) ...", len(months))
    for year, month in months:
        log.info("── %d-%02d ──", year, month)
        _transform_weather(year, month)
        _transform_aq(year, month)

    log.info("── Traffic backfill ──")
    _transform_traffic()

    log.info("Transform complete.")


if __name__ == "__main__":
    main()
