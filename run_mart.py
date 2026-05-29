#!/usr/bin/env python3
"""Build dashboard-ready mart tables from the intermediate layer.

Reads all files from data/intermediate/, concatenates each source, and writes
three mart parquet files to data/mart/:

    mart_weather.parquet   — hourly weather per station × hour
    mart_aq.parquet        — hourly AQ per station × hour (all pollutants)
    mart_traffic.parquet   — hourly traffic per detector × hour
    dim_stations.parquet   — combined station/detector metadata for the map

Mart tables are always rebuilt from intermediate (idempotent, can be re-run
at any time without data loss — intermediate is the source of truth).

Usage:
    python run_mart.py
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)

_INTERMEDIATE = Path("data/intermediate")
_MART         = Path("data/mart")
_STAGING      = Path("data/staging")


def _concat_monthly(pattern: str, label: str) -> pd.DataFrame:
    files = sorted(_INTERMEDIATE.glob(pattern))
    if not files:
        log.warning("No intermediate files matching %s", pattern)
        return pd.DataFrame()
    parts = [pd.read_parquet(f) for f in files]
    df = pd.concat(parts, ignore_index=True)
    log.info("%s: %d rows from %d file(s)", label, len(df), len(files))
    return df


def build_mart_weather() -> None:
    df = _concat_monthly("weather_*.parquet", "mart_weather")
    if df.empty:
        return
    df = df.drop_duplicates(subset=["station_id", "obs_time"]).sort_values(
        ["area", "station_id", "obs_time"]
    )
    path = _MART / "mart_weather.parquet"
    df.to_parquet(path, index=False)
    log.info("Written %d rows → %s", len(df), path)


def build_mart_aq() -> None:
    df = _concat_monthly("air_quality_*.parquet", "mart_aq")
    if df.empty:
        return
    df = df.drop_duplicates(subset=["station_id", "obs_time"]).sort_values(
        ["area", "station_id", "obs_time"]
    )
    path = _MART / "mart_aq.parquet"
    df.to_parquet(path, index=False)
    log.info("Written %d rows → %s", len(df), path)


def build_mart_traffic() -> None:
    traffic_path = _INTERMEDIATE / "traffic.parquet"
    if not traffic_path.exists():
        log.warning("No intermediate/traffic.parquet found")
        return
    df = pd.read_parquet(traffic_path)
    df = df.drop_duplicates(subset=["detector_id", "obs_time"]).sort_values(
        ["area", "detector_id", "obs_time"]
    )
    path = _MART / "mart_traffic.parquet"
    df.to_parquet(path, index=False)
    log.info("Written %d rows → %s", len(df), path)


def build_dim_stations() -> None:
    """Combined station/detector metadata for the map layer."""
    frames: list[pd.DataFrame] = []

    # Weather stations
    ws_path = _STAGING / "weather_stations.parquet"
    if ws_path.exists():
        ws = pd.read_parquet(ws_path).drop_duplicates(subset=["jaam_kood"])
        ws_out = ws.rename(columns={"jaam_kood": "station_id", "jaam_nimi": "station_name",
                                    "laiuskraad": "lat", "pikkuskraad": "lon"})
        ws_out["source"] = "weather"
        ws_out["area"]   = ws_out["station_id"].map({
            "AJHARK01": "tallinn", "AJTART01": "tartu", "AJNARV01": "narva"
        })
        keep = [c for c in ["station_id","station_name","area","lat","lon","source"]
                if c in ws_out.columns]
        frames.append(ws_out[keep])

    # AQ stations (hardcoded from ohuseire metadata)
    aq_meta = {
        4: {"station_id": "4", "station_name": "Narva",     "area": "narva",
            "lat": 59.3722, "lon": 28.2007},
        5: {"station_id": "5", "station_name": "Liivalaia", "area": "tallinn",
            "lat": 59.4310, "lon": 24.7605},
        7: {"station_id": "7", "station_name": "Õismäe",   "area": "tallinn",
            "lat": 59.4140, "lon": 24.6497},
        8: {"station_id": "8", "station_name": "Tartu",     "area": "tartu",
            "lat": 58.3706, "lon": 26.7348},
    }
    aq_df = pd.DataFrame(aq_meta.values())
    aq_df["source"] = "air_quality"
    frames.append(aq_df)

    # Traffic detectors
    reg_path = _STAGING / "traffic_detector_registry.parquet"
    if reg_path.exists():
        reg = pd.read_parquet(reg_path).rename(
            columns={"traffic_detector_id": "station_id", "site_name": "station_name"}
        )
        reg["source"] = "traffic"
        keep = [c for c in ["station_id","station_name","area","lat","lon","source"]
                if c in reg.columns]
        frames.append(reg[keep])

    if not frames:
        log.warning("No station metadata available for dim_stations")
        return

    dim = pd.concat(frames, ignore_index=True)
    path = _MART / "dim_stations.parquet"
    dim.to_parquet(path, index=False)
    log.info("dim_stations: %d rows → %s", len(dim), path)


def main() -> None:
    _MART.mkdir(parents=True, exist_ok=True)
    build_mart_weather()
    build_mart_aq()
    build_mart_traffic()
    build_dim_stations()
    log.info("Mart build complete.")


if __name__ == "__main__":
    main()
