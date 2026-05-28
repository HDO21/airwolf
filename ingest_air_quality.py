#!/usr/bin/env python3
"""Ingest hourly air-quality observations for the three study areas.

Fetches from f_keskkonnaseire month-by-month, converts coordinates to EPSG:3301,
filters to study area bounding boxes, pivots to one row per station × hour, and
writes staging/air_quality_raw_YYYY_MM.parquet.

Usage:
    python ingest_air_quality.py 2024 1 2025 12
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from pyproj import Transformer

from validate import validate

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)

_BASE_URL = "https://keskkonnaandmed.envir.ee"
_HEADERS = {"Accept-Profile": "apijahialad", "Accept": "application/json"}
_STAGING = Path("staging")
_TIMEOUT = 30
_MAX_RETRIES = 3
_BACKOFF = 5

# Estonian pollutant names → short codes
_POLLUTANT_MAP: dict[str, str] = {
    "Osoon": "O3",
    "Lämmastikdioksiid": "NO2",
    "Peened osakesed (PM 10)": "PM10",
    "Eriti peened osakesed (PM 2,5)": "PM25",
}
# Three pollutants whose names have no comma — safe to include in in.()
_SAFE_POLLUTANTS = ["Osoon", "Lämmastikdioksiid", "Peened osakesed (PM 10)"]
# PM2,5 name contains a comma which would break PostgREST in.() parsing,
# so it is fetched with a separate eq. filter.
_PM25_NAME = "Eriti peened osakesed (PM 2,5)"

# Study area bounding boxes in EPSG:3301
STUDY_AREAS: dict[str, dict[str, int]] = {
    "tallinn": {"x_min": 526818, "x_max": 557609, "y_min": 6580812, "y_max": 6601992},
    "narva":   {"x_min": 732765, "x_max": 739464, "y_min": 6585793, "y_max": 6591660},
    "tartu":   {"x_min": 643432, "x_max": 663197, "y_min": 6459800, "y_max": 6478907},
}

_wgs84_to_3301 = Transformer.from_crs("EPSG:4326", "EPSG:3301", always_xy=True)
_3301_to_wgs84 = Transformer.from_crs("EPSG:3301", "EPSG:4326", always_xy=True)

_OUT_COLS = ["seirekoha_kood", "obs_time", "area", "lat", "lon", "O3", "NO2", "PM10", "PM25"]


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


def _month_range(y1: int, m1: int, y2: int, m2: int):
    y, m = y1, m1
    while (y, m) <= (y2, m2):
        yield y, m
        m += 1
        if m > 12:
            m, y = 1, y + 1


def _fetch_month(year: int, month: int) -> pd.DataFrame:
    start = f"{year}-{month:02d}-01T00:00:00"
    end_year, end_month = (year + 1, 1) if month == 12 else (year, month + 1)
    end = f"{end_year}-{end_month:02d}-01T00:00:00"

    base: list[tuple[str, Any]] = [
        ("seiretoo_seotud_programmi_nimi_ii", "in.(Välisõhu seire)"),
        ("seireaeg_algus", f"gte.{start}"),
        ("seireaeg_algus", f"lt.{end}"),
    ]

    log.info("Fetching air quality for %d-%02d ...", year, month)

    safe_names = ",".join(_SAFE_POLLUTANTS)
    rows = _get("f_keskkonnaseire", base + [("naitaja_nimetus", f"in.({safe_names})")])

    pm25_rows = _get("f_keskkonnaseire", base + [("naitaja_nimetus", f"eq.{_PM25_NAME}")])

    combined = rows + pm25_rows
    log.info("Received %d raw rows for %d-%02d (%d main + %d PM2.5)",
             len(combined), year, month, len(rows), len(pm25_rows))
    return pd.DataFrame(combined) if combined else pd.DataFrame()


def _resolve_coords_3301(station_df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Return (x_easting, y_northing) in EPSG:3301 for each row of station_df."""
    idx = station_df.index
    x = pd.Series(float("nan"), index=idx)
    y = pd.Series(float("nan"), index=idx)

    # kesk_x / kesk_y — check value range to confirm orientation
    if "kesk_x" in station_df.columns and "kesk_y" in station_df.columns:
        cx = pd.to_numeric(station_df["kesk_x"], errors="coerce")
        cy = pd.to_numeric(station_df["kesk_y"], errors="coerce")
        valid = cx.notna() & cy.notna()
        if valid.any():
            # Typical Estonian easting ~300k–800k, northing ~6.4M–6.8M
            is_east_x = cx[valid].between(200_000, 900_000).mean() > 0.5
            if is_east_x:
                x[valid], y[valid] = cx[valid], cy[valid]
            else:
                x[valid], y[valid] = cy[valid], cx[valid]

    # Fall back to WGS84 lon/lat → convert to 3301
    needs = x.isna()
    lon_col = next((c for c in ["lon", "longitude"] if c in station_df.columns), None)
    lat_col = next((c for c in ["lat", "latitude"] if c in station_df.columns), None)
    if needs.any() and lon_col and lat_col:
        lon = pd.to_numeric(station_df.loc[needs, lon_col], errors="coerce")
        lat = pd.to_numeric(station_df.loc[needs, lat_col], errors="coerce")
        valid2 = lon.notna() & lat.notna()
        if valid2.any():
            xs, ys = _wgs84_to_3301.transform(lon[valid2].to_numpy(), lat[valid2].to_numpy())
            x.loc[needs & (lon.notna() & lat.notna())] = xs
            y.loc[needs & (lon.notna() & lat.notna())] = ys

    return x, y


def _resolve_coords_wgs84(station_df: pd.DataFrame, x_3301: pd.Series, y_3301: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Return (lon, lat) WGS84 for each row, preferring original if present."""
    idx = station_df.index
    out_lon = pd.Series(float("nan"), index=idx)
    out_lat = pd.Series(float("nan"), index=idx)

    lon_col = next((c for c in ["lon", "longitude"] if c in station_df.columns), None)
    lat_col = next((c for c in ["lat", "latitude"] if c in station_df.columns), None)
    if lon_col and lat_col:
        lon = pd.to_numeric(station_df[lon_col], errors="coerce")
        lat = pd.to_numeric(station_df[lat_col], errors="coerce")
        valid = lon.between(20.0, 30.0) & lat.between(57.0, 62.0)
        out_lon[valid], out_lat[valid] = lon[valid], lat[valid]

    # Convert 3301 → WGS84 for anything still missing
    still_missing = out_lon.isna() & x_3301.notna() & y_3301.notna()
    if still_missing.any():
        lons, lats = _3301_to_wgs84.transform(
            x_3301[still_missing].to_numpy(),
            y_3301[still_missing].to_numpy(),
        )
        out_lon[still_missing] = lons
        out_lat[still_missing] = lats

    return out_lon, out_lat


def _area_for_point(x: float, y: float) -> str | None:
    for name, bb in STUDY_AREAS.items():
        if bb["x_min"] <= x <= bb["x_max"] and bb["y_min"] <= y <= bb["y_max"]:
            return name
    return None


def _process(raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty or "seirekoha_kood" not in raw.columns:
        return pd.DataFrame(columns=_OUT_COLS)

    raw = raw.copy()

    # Build per-station coordinate lookup
    station_df = raw.drop_duplicates(subset=["seirekoha_kood"]).copy()
    x_3301, y_3301 = _resolve_coords_3301(station_df)
    out_lon, out_lat = _resolve_coords_wgs84(station_df, x_3301, y_3301)

    station_df = station_df.assign(x_3301=x_3301, y_3301=y_3301, out_lon=out_lon, out_lat=out_lat)
    station_df["area"] = station_df.apply(
        lambda r: _area_for_point(r["x_3301"], r["y_3301"])
        if pd.notna(r.get("x_3301")) and pd.notna(r.get("y_3301")) else None,
        axis=1,
    )

    in_area = station_df[station_df["area"].notna()].copy()
    if in_area.empty:
        log.warning("No monitoring stations found within any study area BBOX")
        return pd.DataFrame(columns=_OUT_COLS)

    station_lookup: dict[str, dict] = in_area.set_index("seirekoha_kood")[
        ["area", "out_lon", "out_lat"]
    ].to_dict("index")
    log.info("Stations within study areas: %d — %s", len(station_lookup), list(station_lookup))

    # Filter measurements to study-area stations
    raw = raw[raw["seirekoha_kood"].isin(station_lookup)].copy()
    raw["pollutant"] = raw["naitaja_nimetus"].map(_POLLUTANT_MAP)
    raw = raw.dropna(subset=["pollutant"])
    raw["tulemus_arvuline"] = pd.to_numeric(raw["tulemus_arvuline"], errors="coerce")
    raw["obs_time"] = pd.to_datetime(raw["seireaeg_algus"], utc=True, errors="coerce")
    raw = raw.dropna(subset=["obs_time"])

    if raw.empty:
        return pd.DataFrame(columns=_OUT_COLS)

    pivoted = raw.pivot_table(
        index=["seirekoha_kood", "obs_time"],
        columns="pollutant",
        values="tulemus_arvuline",
        aggfunc="mean",
    ).reset_index()
    pivoted.columns.name = None

    for col in ["O3", "NO2", "PM10", "PM25"]:
        if col not in pivoted.columns:
            pivoted[col] = float("nan")

    pivoted["area"] = pivoted["seirekoha_kood"].map(lambda k: station_lookup.get(k, {}).get("area"))
    pivoted["lon"] = pivoted["seirekoha_kood"].map(lambda k: station_lookup.get(k, {}).get("out_lon"))
    pivoted["lat"] = pivoted["seirekoha_kood"].map(lambda k: station_lookup.get(k, {}).get("out_lat"))

    return pivoted[_OUT_COLS].copy()


def main() -> None:
    if len(sys.argv) != 5:
        print("Usage: python ingest_air_quality.py <year_start> <month_start> <year_end> <month_end>",
              file=sys.stderr)
        sys.exit(1)

    y1, m1, y2, m2 = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
    _STAGING.mkdir(exist_ok=True)

    for year, month in _month_range(y1, m1, y2, m2):
        raw = _fetch_month(year, month)
        out = _process(raw)
        vr = validate(out, "air_quality")
        log.info("Validation %d-%02d: passed=%s  issues=%d", year, month, vr["passed"], len(vr["issues"]))
        path = _STAGING / f"air_quality_raw_{year}_{month:02d}.parquet"
        out.to_parquet(path, index=False)
        log.info("Written %d rows to %s", len(out), path)


if __name__ == "__main__":
    main()
