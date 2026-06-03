#!/usr/bin/env python3
from __future__ import annotations

import logging
import time
from typing import Any

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

# f_kliima_tund element_kood -> staging.weather_raw column
ELEMENT_TO_COLUMN = {
    "TA": "temperature_c",
    "WS10M": "wind_speed_ms",
    "WD10M": "wind_direction_deg",
    "PR1H": "precip_mm",
}


def _get(endpoint: str, params: list[tuple[str, Any]]) -> list[dict[str, Any]]:
    """Fetch rows from Keskkonnaandmed API."""
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
    """Find the API column containing the measured value."""
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


def _fetch_station_coordinates() -> pd.DataFrame:
    """Fetch station metadata and return columns: jaam_kood, lat, lon."""
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
    """Fetch hourly observations for one month."""
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
    run_id: str,
) -> list[tuple]:
    """
    Convert API rows from long format into staging.weather_raw format.

    API format:
        jaam_kood | aasta | kuu | paev | tund | element_kood | vaartus

    DB format:
        run_id | jaam_kood | obs_time | lat | lon |
        temperature_c | wind_speed_ms | wind_direction_deg | precip_mm
    """
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
    Load weather data directly into PostgreSQL.

    Intended Airflow usage:
        from ingestion.ingest_weather import load_weather

        load_weather(
            hook=PostgresHook(postgres_conn_id="analytics_db"),
            run_id=<uuid string>,
            year_start=2025,
            month_start=1,
            year_end=2025,
            month_end=12,
            schema="staging",
        )
    """
    stations_df = _fetch_station_coordinates()

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

        m += 1
        if m > 12:
            m = 1
            y += 1

    log.info("Inserted %d weather rows in total", total_inserted)
    return total_inserted


def _upsert_parquet(path: "Path", new_df: pd.DataFrame, pk: list[str]) -> None:
    from pathlib import Path as _Path
    path = _Path(path)
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


def main_cli() -> None:
    """Parquet-based CLI entry point for the staging pipeline.

    Usage:
        python ingest_weather.py 2025 12
        python ingest_weather.py 2025 1 2025 11
    """
    import datetime
    import sys
    from pathlib import Path

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    argv = sys.argv[1:]
    if len(argv) == 2:
        y1, m1, y2, m2 = int(argv[0]), int(argv[1]), int(argv[0]), int(argv[1])
    elif len(argv) == 4:
        y1, m1, y2, m2 = int(argv[0]), int(argv[1]), int(argv[2]), int(argv[3])
    else:
        print("Usage: python ingest_weather.py <year> <month> [year_end month_end]",
              file=sys.stderr)
        sys.exit(1)

    staging = Path("data/staging")
    staging.mkdir(parents=True, exist_ok=True)

    # Station coordinates
    stations_df = _fetch_station_coordinates()
    if not stations_df.empty:
        stations_out = stations_df.copy()
        stations_out["_ingested_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        _upsert_parquet(staging / "weather_stations.parquet", stations_out, pk=["jaam_kood"])

    # Observations — keep raw long format
    y, m = y1, m1
    while (y, m) <= (y2, m2):
        obs_df = _fetch_observations(y, m)
        if not obs_df.empty:
            obs_df["_ingested_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            _upsert_parquet(
                staging / f"weather_raw_{y}_{m:02d}.parquet",
                obs_df,
                pk=["jaam_kood", "aasta", "kuu", "paev", "tund", "element_kood"],
            )
        m += 1
        if m > 12:
            m, y = 1, y + 1


if __name__ == "__main__":
    main_cli()
