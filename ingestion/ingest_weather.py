#!/usr/bin/env python3
from __future__ import annotations

import logging
import time
from typing import Any
import uuid

import pandas as pd
import requests

log = logging.getLogger(__name__)

BASE_URL = "https://keskkonnaandmed.envir.ee"
HEADERS = {
    "Accept-Profile": "apijahiala",
    "Accept": "application/json",
}
TIMEOUT = 30
MAX_RETRIES = 3
BACKOFF = 5

STATION_CODES = ["AJHARK01", "AJTART01", "AJNARV01"]
ELEMENT_CODES = ["TA", "WS10M", "WD10M", "PR1H"]

ELEMENT_TO_COLUMN = {
    "TA": "temperature_c",
    "WS10M": "wind_speed_ms",
    "WD10M": "wind_direction_deg",
    "PR1H": "precip_mm",
}


def _get(endpoint: str, params: list[tuple[str, Any]]) -> list[dict[str, Any]]:
    url = f"{BASE_URL}/{endpoint.lstrip('/')}"
    all_params = params + [("limit", "50000")]

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(
                url,
                params=all_params,
                headers=HEADERS,
                timeout=TIMEOUT,
            )

            if resp.status_code >= 500:
                raise requests.HTTPError(response=resp)

            resp.raise_for_status()
            data = resp.json()

            if not isinstance(data, list):
                raise ValueError(f"Expected list response from {url}, got {type(data)}")

            return data

        except (requests.HTTPError, requests.ConnectionError, requests.Timeout) as exc:
            if attempt == MAX_RETRIES:
                raise

            log.warning(
                "Attempt %d/%d failed: %s — retrying in %ds",
                attempt,
                MAX_RETRIES,
                exc,
                BACKOFF,
            )
            time.sleep(BACKOFF)

    return []


def _find_value_column(df: pd.DataFrame) -> str:
    candidates = [
        "vaartus",
        "väärtus",
        "value",
        "sisu",
        "element_vaartus",
        "tulemus",
    ]

    for col in candidates:
        if col in df.columns:
            return col

    raise ValueError(
        "Could not find weather value column. "
        f"Available columns: {list(df.columns)}"
    )


def _fetch_station_metadata() -> pd.DataFrame:
    """
    Pärib jaamade lat/lon info.
    NB! Seda EI salvestata enam eraldi weather_stations_raw tabelisse.
    Seda kasutatakse ainult weather_raw ridade rikastamiseks.
    """
    codes = ",".join(STATION_CODES)

    rows = _get(
        "f_kliima_jaam_vaatlus",
        [
            ("jaam_kood", f"in.({codes})"),
            ("jaam_periood_lopp", "eq.3999-12-31T23:59:00"),
        ],
    )

    if not rows:
        rows = _get(
            "f_kliima_jaam_vaatlus",
            [("jaam_kood", f"in.({codes})")],
        )

    if not rows:
        log.warning("No weather station metadata returned")
        return pd.DataFrame(columns=["jaam_kood", "lat", "lon"])

    df = pd.DataFrame(rows)

    if "jaam_kood" not in df.columns:
        raise ValueError(
            "Station metadata response does not contain 'jaam_kood'. "
            f"Available columns: {list(df.columns)}"
        )

    lat_candidates = [
        "lat",
        "latitude",
        "laiuskraad",
        "jaam_laius",
        "jaam_laiuskraad",
        "koordinaat_laius",
    ]
    lon_candidates = [
        "lon",
        "longitude",
        "pikkuskraad",
        "jaam_pikkus",
        "jaam_pikkuskraad",
        "koordinaat_pikkus",
    ]

    lat_col = next((col for col in lat_candidates if col in df.columns), None)
    lon_col = next((col for col in lon_candidates if col in df.columns), None)

    out = pd.DataFrame()
    out["jaam_kood"] = df["jaam_kood"].astype(str)

    if lat_col:
        out["lat"] = pd.to_numeric(df[lat_col], errors="coerce")
    else:
        out["lat"] = None
        log.warning("Could not find latitude column. Available columns: %s", list(df.columns))

    if lon_col:
        out["lon"] = pd.to_numeric(df[lon_col], errors="coerce")
    else:
        out["lon"] = None
        log.warning("Could not find longitude column. Available columns: %s", list(df.columns))

    return out.drop_duplicates(subset=["jaam_kood"])


def _fetch_observations(year: int, month: int) -> pd.DataFrame:
    rows = _get(
        "f_kliima_tund",
        [
            ("aasta", f"eq.{year}"),
            ("kuu", f"eq.{month}"),
            ("jaam_kood", f"in.({','.join(STATION_CODES)})"),
            ("element_kood", f"in.({','.join(ELEMENT_CODES)})"),
        ],
    )

    if not rows:
        log.warning("No weather observations returned for %d-%02d", year, month)
        return pd.DataFrame()

    return pd.DataFrame(rows)


def _prepare_weather_rows(
    observations_df: pd.DataFrame,
    stations_df: pd.DataFrame,
    run_id: uuid.UUID,
) -> list[tuple]:
    if observations_df.empty:
        return []

    df = observations_df.copy()

    required = ["jaam_kood", "aasta", "kuu", "paev", "tund", "element_kood"]
    missing = [col for col in required if col not in df.columns]

    if missing:
        raise ValueError(
            f"Weather API response missing required columns: {missing}. "
            f"Available columns: {list(df.columns)}"
        )

    value_col = _find_value_column(df)

    df["obs_time"] = pd.to_datetime(
        df["aasta"].astype(str)
        + "-"
        + df["kuu"].astype(str).str.zfill(2)
        + "-"
        + df["paev"].astype(str).str.zfill(2)
        + " "
        + df["tund"].astype(str).str.zfill(2)
        + ":00:00",
        errors="coerce",
    )

    df[value_col] = pd.to_numeric(df[value_col], errors="coerce")

    wide = (
        df.pivot_table(
            index=["jaam_kood", "obs_time"],
            columns="element_kood",
            values=value_col,
            aggfunc="first",
        )
        .reset_index()
        .rename_axis(None, axis=1)
    )

    wide = wide.rename(columns=ELEMENT_TO_COLUMN)

    if not stations_df.empty:
        stations = stations_df[["jaam_kood", "lat", "lon"]].drop_duplicates("jaam_kood")
        wide["jaam_kood"] = wide["jaam_kood"].astype(str)
        wide = wide.merge(stations, on="jaam_kood", how="left")
    else:
        wide["lat"] = None
        wide["lon"] = None

    output_cols = [
        "temperature_c",
        "wind_speed_ms",
        "wind_direction_deg",
        "precip_mm",
        "lat",
        "lon",
    ]

    for col in output_cols:
        if col not in wide.columns:
            wide[col] = None

    wide = wide.dropna(subset=["jaam_kood", "obs_time"])

    rows: list[tuple] = []

    for _, row in wide.iterrows():
        rows.append(
            (
                run_id,
                row["jaam_kood"],
                row["obs_time"].to_pydatetime(),
                None if pd.isna(row["lat"]) else float(row["lat"]),
                None if pd.isna(row["lon"]) else float(row["lon"]),
                None if pd.isna(row["temperature_c"]) else float(row["temperature_c"]),
                None if pd.isna(row["wind_speed_ms"]) else float(row["wind_speed_ms"]),
                None if pd.isna(row["wind_direction_deg"]) else float(row["wind_direction_deg"]),
                None if pd.isna(row["precip_mm"]) else float(row["precip_mm"]),
            )
        )

    return rows


def load_weather(
    hook,
    run_id: str,
    year_start: int = 2025,
    month_start: int = 1,
    year_end: int = 2025,
    month_end: int = 12,
    schema: str = "staging",
) -> int:
    """
    Laeb ilmaandmed staging.weather_raw tabelisse.

    Eraldi weather_stations_raw tabelit enam ei kasutata.
    Jaamade lat/lon lisatakse otse weather_raw ridadele.
    """
    stations_df = _fetch_station_metadata()

    y, m = year_start, month_start
    total_inserted = 0

    while (y, m) <= (year_end, month_end):
        observations_df = _fetch_observations(y, m)

        rows = _prepare_weather_rows(
            observations_df=observations_df,
            stations_df=stations_df,
            run_id=run_id,
        )

        if rows:
            hook.insert_rows(
                table=f"{schema}.weather_raw",
                rows=rows,
                target_fields=[
                    "run_id",
                    "jaam_kood",
                    "obs_time",
                    "lat",
                    "lon",
                    "temperature_c",
                    "wind_speed_ms",
                    "wind_direction_deg",
                    "precip_mm",
                ],
                replace=False,
            )

            total_inserted += len(rows)
            log.info("Inserted %d weather rows for %d-%02d", len(rows), y, m)
        else:
            log.info("No weather rows to insert for %d-%02d", y, m)

        m += 1
        if m > 12:
            m = 1
            y += 1

    log.info("Inserted %d weather rows in total", total_inserted)
    return total_inserted


if __name__ == "__main__":
    raise SystemExit(
        "This module is intended to be called by Airflow. "
        "Use load_weather(hook=..., run_id=..., ...) from dags/airwolf_pipeline.py."
    )