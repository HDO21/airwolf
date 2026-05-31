#!/usr/bin/env python3
from __future__ import annotations

import calendar
import logging
import time
from contextlib import closing
from datetime import datetime, timedelta
from typing import Any, Iterable

import pandas as pd
import requests

log = logging.getLogger(__name__)

BASE_URL = "https://ohuseire.ee/api/monitoring/et"
HEADERS = {"Accept": "application/json"}
TIMEOUT = 30
MAX_RETRIES = 3
BACKOFF = 5

# Jaamad: Narva, Liivalaia, Õismäe, Tartu
STATION_IDS = [4, 5, 7, 8]

# Näitajad: SO2, NO2, O3, PM10, PM2.5
INDICATOR_IDS = [1, 3, 6, 21, 23]


def _get(params: dict[str, Any]) -> list[dict[str, Any]]:
    """GET päring Õhuseire API vastu retry loogikaga."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(
                BASE_URL,
                params=params,
                headers=HEADERS,
                timeout=TIMEOUT,
            )

            if resp.status_code >= 500:
                raise requests.HTTPError(response=resp)

            resp.raise_for_status()
            data = resp.json()

            if not isinstance(data, list):
                raise ValueError(
                    f"Expected list response from {BASE_URL}, got {type(data)}"
                )

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


def _month_iter(
    year_start: int,
    month_start: int,
    year_end: int,
    month_end: int,
) -> Iterable[tuple[int, int]]:
    y, m = year_start, month_start

    while (y, m) <= (year_end, month_end):
        yield y, m

        m += 1
        if m > 12:
            m = 1
            y += 1


def _api_date(value: datetime) -> str:
    return value.strftime("%d.%m.%Y")


def _fetch_observations_for_period(start_time: datetime, end_time: datetime) -> pd.DataFrame:
    """
    Pärib õhukvaliteedi andmed etteantud perioodi kohta.

    API range on kuupäevapõhine kujul:
        dd.mm.yyyy,dd.mm.yyyy
    """
    range_str = f"{_api_date(start_time)},{_api_date(end_time)}"

    rows = _get(
        {
            "indicators": ",".join(map(str, INDICATOR_IDS)),
            "range": range_str,
            "resolution": "+",
            "stations": ",".join(map(str, STATION_IDS)),
            "type": "INDICATOR",
        }
    )

    if not rows:
        log.warning("No air-quality observations returned for %s", range_str)
        return pd.DataFrame()

    return pd.DataFrame(rows)


def _fetch_observations(year: int, month: int) -> pd.DataFrame:
    """
    Pärib ühe kuu õhukvaliteedi andmed.
    Backfill käib kuu kaupa.
    """
    last_day = calendar.monthrange(year, month)[1]

    start_time = datetime(year, month, 1)
    end_time = datetime(year, month, last_day, 23, 59, 59)

    return _fetch_observations_for_period(start_time, end_time)


def _find_column(df: pd.DataFrame, candidates: list[str], logical_name: str) -> str:
    for col in candidates:
        if col in df.columns:
            return col

    raise ValueError(
        f"Could not find air-quality {logical_name} column. "
        f"Available columns: {list(df.columns)}"
    )


def _find_optional_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for col in candidates:
        if col in df.columns:
            return col
    return None


def _prepare_air_quality_rows(
    observations_df: pd.DataFrame,
    run_id: str,
) -> list[tuple]:
    """
    Teeb API ridadest staging.air_quality_raw tabelisse sobivad tuple'id.

    Eeldatav tabel:
        staging.air_quality_raw(
            run_id,
            station,
            indicator,
            measured,
            value,
            loaded_at
        )
    """
    if observations_df.empty:
        return []

    df = observations_df.copy()

    station_col = _find_column(
        df,
        ["station", "station_id", "stationId", "stationName", "station_name", "jaam", "jaam_id"],
        "station",
    )

    indicator_col = _find_column(
        df,
        ["indicator", "indicator_id", "indicatorId", "indicatorName", "indicator_name", "parameter"],
        "indicator",
    )

    measured_col = _find_column(
        df,
        ["measured", "time", "timestamp", "date", "datetime", "measurement_time"],
        "measured",
    )

    value_col = _find_column(
        df,
        ["value", "val", "result", "measurement", "measured_value", "avg", "average"],
        "value",
    )

    df["station_out"] = df[station_col].astype(str)
    df["indicator_out"] = df[indicator_col].astype(str)
    df["measured_out"] = pd.to_datetime(df[measured_col], errors="coerce")
    df["value_out"] = pd.to_numeric(df[value_col], errors="coerce")

    df = df.dropna(subset=["station_out", "indicator_out", "measured_out"])

    rows: list[tuple] = []

    for _, row in df.iterrows():
        rows.append(
            (
                str(run_id),
                row["station_out"],
                row["indicator_out"],
                row["measured_out"].to_pydatetime(),
                None if pd.isna(row["value_out"]) else float(row["value_out"]),
            )
        )

    return rows


def _upsert_air_quality_rows(hook, rows: list[tuple], schema: str = "staging") -> int:
    """
    Lisab või uuendab staging.air_quality_raw read.

    Eeldus andmebaasis:
        PRIMARY KEY (station, indicator, measured)
    või:
        UNIQUE (station, indicator, measured)
    """
    if not rows:
        return 0

    sql = f"""
        INSERT INTO {schema}.air_quality_raw
            (run_id, station, indicator, measured, value, loaded_at)
        VALUES
            (%s, %s, %s, %s, %s, NOW())
        ON CONFLICT (station, indicator, measured) DO UPDATE SET
            run_id = EXCLUDED.run_id,
            value = EXCLUDED.value,
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
    """
    Filtreerib prepared rows listi measured aja järgi.
    Tuple'is on measured indeksil 3.
    """
    filtered: list[tuple] = []

    for row in rows:
        measured = row[3]

        if start_time is not None and measured < start_time:
            continue

        if end_time is not None and measured > end_time:
            continue

        filtered.append(row)

    return filtered


def load_air_quality_backfill(
    hook,
    run_id: str,
    year_start: int = 2026,
    month_start: int = 3,
    year_end: int | None = None,
    month_end: int | None = None,
    schema: str = "staging",
) -> int:
    """
    Backfill: laeb kuu-vahemiku staging.air_quality_raw tabelisse.

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

    total_upserted = 0

    for y, m in _month_iter(year_start, month_start, year_end, month_end):
        observations_df = _fetch_observations(y, m)

        rows = _prepare_air_quality_rows(
        observations_df=observations_df,
        run_id=run_id,
        )

        # Ära salvesta tuleviku mõõtmisi.
        # Eriti oluline jooksva kuu backfilli puhul, sest kuu päring küsib kuu lõpuni.
        now_time = datetime.today().replace(microsecond=0)

        rows = _filter_rows_by_time(
            rows,
            end_time=now_time,
        )

        upserted = _upsert_air_quality_rows(
            hook=hook,
            rows=rows,
            schema=schema,
        )

        total_upserted += upserted

        log.info(
            "Backfill upserted %d air-quality rows for %d-%02d",
            upserted,
            y,
            m,
        )

    log.info("Backfill upserted %d air-quality rows in total", total_upserted)
    return total_upserted


def load_air_quality_recent(
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

    total_upserted = 0

    for y, m in _month_iter(
        start_time.year,
        start_time.month,
        end_time.year,
        end_time.month,
    ):
        observations_df = _fetch_observations(y, m)

        rows = _prepare_air_quality_rows(
            observations_df=observations_df,
            run_id=run_id,
        )

        rows = _filter_rows_by_time(
            rows,
            start_time=start_time,
            end_time=end_time,
        )

        upserted = _upsert_air_quality_rows(
            hook=hook,
            rows=rows,
            schema=schema,
        )

        total_upserted += upserted

        log.info(
            "Recent load upserted %d air-quality rows for %d-%02d between %s and %s",
            upserted,
            y,
            m,
            start_time,
            end_time,
        )

    log.info("Recent load upserted %d air-quality rows in total", total_upserted)
    return total_upserted


# Tagasiühilduv alias, kui mõnes DAG-is on veel load_air_quality import.
def load_air_quality(*args, **kwargs) -> int:
    return load_air_quality_backfill(*args, **kwargs)


if __name__ == "__main__":
    raise SystemExit(
        "This module is intended to be called by Airflow. "
        "Use load_air_quality_backfill(...) for backfill and "
        "load_air_quality_recent(...) for hourly updates."
    )