#!/usr/bin/env python3
"""Ingest hourly weather observations for Tallinn-Harku, Tartu-Tõravere, and Narva.

Fetches from f_kliima_tund, pivots to one row per station × hour, and writes
a parquet file to staging/weather_raw_YYYY_MM.parquet.

Usage:
    python ingest_weather.py 2025 12
"""
from __future__ import annotations

import logging
import sys
import time
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

_BASE_URL = "https://keskkonnaandmed.envir.ee"
_HEADERS = {"Accept-Profile": "apijahialad", "Accept": "application/json"}
_STATION_CODES = ["AJHARK01", "AJTART01", "AJNARV01"]
_ELEMENT_CODES = ["TA", "WS", "WD", "DPREC"]
_ELEMENT_TO_COL: dict[str, str] = {
    "TA": "temperature_c",
    "WS": "wind_speed_ms",
    "WD": "wind_direction_deg",
    "DPREC": "precip_mm",
}
_STAGING = Path("staging")
_TIMEOUT = 30
_MAX_RETRIES = 3
_BACKOFF = 5
_OUT_COLS = ["jaam_kood", "obs_time", "lat", "lon",
             "temperature_c", "wind_speed_ms", "wind_direction_deg", "precip_mm"]


def _get(endpoint: str, params: list[tuple[str, Any]]) -> list[dict]:
    url = f"{_BASE_URL}/{endpoint.lstrip('/')}"
    all_params = params + [("limit", "10000")]
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = requests.get(url, params=all_params, headers=_HEADERS, timeout=_TIMEOUT)
            if resp.status_code >= 500:
                raise requests.HTTPError(response=resp)
            resp.raise_for_status()
            return resp.json()
        except (requests.HTTPError, requests.ConnectionError) as exc:
            if attempt == _MAX_RETRIES:
                raise
            log.warning("Attempt %d/%d failed: %s — retrying in %ds", attempt, _MAX_RETRIES, exc, _BACKOFF)
            time.sleep(_BACKOFF)
    return []


def _fetch_station_coords() -> dict[str, dict[str, float]]:
    codes_str = ",".join(_STATION_CODES)
    log.info("Fetching station coordinates from f_kliima_jaam_vaatlus ...")
    rows = _get(
        "f_kliima_jaam_vaatlus",
        [
            ("jaam_kood", f"in.({codes_str})"),
            ("jaam_periood_lopp", "eq.3999-12-31T23:59:00"),
            ("select", "jaam_kood,laiuskraad,pikkuskraad"),
        ],
    )
    if not rows:
        log.warning("Active-period filter returned no rows; retrying without period filter")
        rows = _get(
            "f_kliima_jaam_vaatlus",
            [
                ("jaam_kood", f"in.({codes_str})"),
                ("select", "jaam_kood,laiuskraad,pikkuskraad"),
            ],
        )

    coords: dict[str, dict[str, float]] = {}
    for row in pd.DataFrame(rows).drop_duplicates(subset=["jaam_kood"]).to_dict("records"):
        jk = row.get("jaam_kood")
        lat = row.get("laiuskraad")
        lon = row.get("pikkuskraad")
        if jk and pd.notna(lat) and pd.notna(lon):
            coords[jk] = {"lat": float(lat), "lon": float(lon)}
    log.info("Coordinates loaded for %d station(s): %s", len(coords), list(coords))
    return coords


def _fetch_raw(year: int, month: int) -> pd.DataFrame:
    codes_str = ",".join(_STATION_CODES)
    elements_str = ",".join(_ELEMENT_CODES)
    log.info("Fetching f_kliima_tund for %d-%02d ...", year, month)
    rows = _get(
        "f_kliima_tund",
        [
            ("aasta", f"eq.{year}"),
            ("kuu", f"eq.{month}"),
            ("jaam_kood", f"in.({codes_str})"),
            ("element_kood", f"in.({elements_str})"),
        ],
    )
    log.info("Received %d raw rows", len(rows))
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _build_output(raw: pd.DataFrame, coords: dict[str, dict[str, float]]) -> pd.DataFrame:
    raw = raw.copy()
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
        columns="col",
        values="vaartus",
        aggfunc="first",
    ).reset_index()
    pivoted.columns.name = None

    for col in ["temperature_c", "wind_speed_ms", "wind_direction_deg", "precip_mm"]:
        if col not in pivoted.columns:
            pivoted[col] = float("nan")

    pivoted["lat"] = pivoted["jaam_kood"].map(lambda k: coords.get(k, {}).get("lat"))
    pivoted["lon"] = pivoted["jaam_kood"].map(lambda k: coords.get(k, {}).get("lon"))

    return pivoted[_OUT_COLS].copy()


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: python ingest_weather.py <year> <month>", file=sys.stderr)
        sys.exit(1)

    year, month = int(sys.argv[1]), int(sys.argv[2])
    _STAGING.mkdir(exist_ok=True)

    coords = _fetch_station_coords()
    raw = _fetch_raw(year, month)

    if raw.empty:
        log.warning("No data returned for %d-%02d", year, month)
        out = pd.DataFrame(columns=_OUT_COLS)
    else:
        out = _build_output(raw, coords)

    vr = validate(out, "weather")
    log.info("Validation: passed=%s  issues=%d", vr["passed"], len(vr["issues"]))

    path = _STAGING / f"weather_raw_{year}_{month:02d}.parquet"
    out.to_parquet(path, index=False)
    log.info("Written %d rows to %s", len(out), path)


if __name__ == "__main__":
    main()
