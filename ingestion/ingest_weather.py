#!/usr/bin/env python3
from __future__ import annotations

import logging
import time
import uuid
from contextlib import closing
from datetime import datetime, timedelta
from typing import Any, Iterable

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

# Vajadusel lisa siia ilmajaamu juurde.
STATION_CODES = ["AJHARK01", "AJTART01", "AJNARV01"]

# TA    = õhutemperatuur
# WS10M = tuule kiirus 10 m kõrgusel
# WD10M = tuule suund 10 m kõrgusel
# PR1H  = 1 tunni sademed
ELEMENT_CODES = ["TA", "WS10M", "WD10M", "PR1H"]

ELEMENT_TO_COLUMN = {
    "TA": "temperature_c",
    "WS10M": "wind_speed_ms",
    "WD10M": "wind_direction_deg",
    "PR1H": "precip_mm",
}


def _get(endpoint: str, params: list[tuple[str, Any]]) -> list[dict[str, Any]]:
    """GET päring Keskkonnaandmete API vastu retry loogikaga."""
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

    Eraldi weather_stations_raw tabelit ei kasutata.
    Koordinaadid lisatakse otse weather_raw ridadele.
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
    """
    Pärib ühe kuu tunnised ilmavaatlused valitud jaamadele ja elementidele.
    API päring käib kuu kaupa, hiljem filtreerime vajadusel obs_time järgi.
    """
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
    run_id: str | uuid.UUID,
) -> list[tuple]:
    """Teeb API ridadest staging.weather_raw tabelisse sobivad tuple'id."""
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


def _month_iter(year_start: int, month_start: int, year_end: int, month_end: int) -> Iterable[tuple[int, int]]:
    y, m = year_start, month_start
    while (y, m) <= (year_end, month_end):
        yield y, m
        m += 1
        if m > 12:
            m = 1
            y += 1


def _upsert_weather_rows(hook, rows: list[tuple], schema: str = "staging") -> int:
    """
    Lisab või uuendab staging.weather_raw read.

    Eeldus andmebaasis:
        PRIMARY KEY (jaam_kood, obs_time)
    või:
        UNIQUE (jaam_kood, obs_time)
    """
    if not rows:
        return 0

    sql = f"""
        INSERT INTO {schema}.weather_raw
            (jaam_kood, obs_time, lat, lon,
             temperature_c, wind_speed_ms, wind_direction_deg, precip_mm, loaded_at)
        VALUES
            (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (jaam_kood, obs_time) DO UPDATE SET
            lat = EXCLUDED.lat,
            lon = EXCLUDED.lon,
            temperature_c = EXCLUDED.temperature_c,
            wind_speed_ms = EXCLUDED.wind_speed_ms,
            wind_direction_deg = EXCLUDED.wind_direction_deg,
            precip_mm = EXCLUDED.precip_mm,
            loaded_at = NOW()
    """

    with closing(hook.get_conn()) as conn:
        with conn:
            with conn.cursor() as cur:
                cur.executemany(sql, rows)

    return len(rows)


def _filter_rows_by_time(
    rows: list[tuple],
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> list[tuple]:
    """Filtreerib prepared rows listi obs_time järgi. Tuple'is on obs_time indeksil 2."""
    filtered: list[tuple] = []

    for row in rows:
        obs_time = row[1]

        if start_time is not None and obs_time < start_time:
            continue
        if end_time is not None and obs_time > end_time:
            continue

        filtered.append(row)

    return filtered


def load_weather_backfill(
    hook,
    run_id: str,
    year_start: int = 2025,
    month_start: int = 1,
    year_end: int | None = None,
    month_end: int | None = None,
    schema: str = "staging",
) -> int:
    """
    Backfill: laeb kuu-vahemiku staging.weather_raw tabelisse.

    Vaikimisi: 2026 märtsist käesoleva kuuni.
    UPSERT tõttu sama perioodi korduv käivitamine ei tekita duplikaate.
    """
    today = datetime.today()
    year_end = year_end if year_end is not None else today.year
    month_end = month_end if month_end is not None else today.month

    if (year_start, month_start) > (year_end, month_end):
        raise ValueError(
            f"Invalid period: start {year_start}-{month_start:02d} is after "
            f"end {year_end}-{month_end:02d}"
        )

    stations_df = _fetch_station_metadata()
    total_upserted = 0

    for y, m in _month_iter(year_start, month_start, year_end, month_end):
        observations_df = _fetch_observations(y, m)
        rows = _prepare_weather_rows(
            observations_df=observations_df,
            stations_df=stations_df,
            run_id=run_id,
        )

        upserted = _upsert_weather_rows(hook=hook, rows=rows, schema=schema)
        total_upserted += upserted
        log.info("Backfill upserted %d weather rows for %d-%02d", upserted, y, m)

    log.info("Backfill upserted %d weather rows in total", total_upserted)
    return total_upserted


def load_weather_recent(
    hook,
    run_id: str,
    lookback_hours: int = 48,
    schema: str = "staging",
) -> int:
    """
    Regulaarne juurde laadimine: sobib tunnipõhisele Airflow schedule'ile.

    Iga käivitusega küsib viimase N tunni andmed ja teeb UPSERT-i.
    Soovitus: 48h aken, sest API andmed võivad viibega tekkida või täieneda.
    """
    if lookback_hours < 1:
        raise ValueError("lookback_hours must be at least 1")

    end_time = datetime.today().replace(minute=0, second=0, microsecond=0)
    start_time = end_time - timedelta(hours=lookback_hours)

    stations_df = _fetch_station_metadata()
    total_upserted = 0

    for y, m in _month_iter(start_time.year, start_time.month, end_time.year, end_time.month):
        observations_df = _fetch_observations(y, m)
        rows = _prepare_weather_rows(
            observations_df=observations_df,
            stations_df=stations_df,
            run_id=run_id,
        )
        rows = _filter_rows_by_time(rows, start_time=start_time, end_time=end_time)

        upserted = _upsert_weather_rows(hook=hook, rows=rows, schema=schema)
        total_upserted += upserted
        log.info(
            "Recent load upserted %d weather rows for %d-%02d between %s and %s",
            upserted,
            y,
            m,
            start_time,
            end_time,
        )

    log.info("Recent load upserted %d weather rows in total", total_upserted)
    return total_upserted


# Tagasiühilduv alias, kui mõnes olemasolevas DAG-is on veel load_weather import.
def load_weather(*args, **kwargs) -> int:
    return load_weather_backfill(*args, **kwargs)


if __name__ == "__main__":
    raise SystemExit(
        "This module is intended to be called by Airflow. "
        "Use load_weather_backfill(...) for backfill and load_weather_recent(...) for hourly updates."
    )
