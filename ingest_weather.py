#!/usr/bin/env python3
"""Ingest raw hourly weather observations into data/staging/.

Fetches from f_kliima_tund and f_kliima_jaam_vaatlus and stores the API
responses with minimal modification. All normalisation, pivoting and validation
are done by run_transform.py.

Staging files are never overwritten: new records are merged and deduplicated
by their natural primary key (jaam_kood × aasta × kuu × paev × tund × element_kood).

Usage:
    python ingest_weather.py 2025 12
"""
from __future__ import annotations

import datetime
import logging
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)

_BASE_URL     = "https://keskkonnaandmed.envir.ee"
_HEADERS      = {"Accept-Profile": "apijahiala", "Accept": "application/json"}
_STAGING      = Path("data/staging")
_TIMEOUT      = 30
_MAX_RETRIES  = 3
_BACKOFF      = 5
_STATION_CODES = ["AJHARK01", "AJTART01", "AJNARV01"]
_ELEMENT_CODES = ["TA", "WS10M", "WD10M", "PR1H"]


def _get(endpoint: str, params: list[tuple[str, Any]]) -> list[dict]:
    url = f"{_BASE_URL}/{endpoint.lstrip('/')}"
    all_params = params + [("limit", "50000")]
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
            log.warning("Attempt %d/%d failed: %s — retrying in %ds",
                        attempt, _MAX_RETRIES, exc, _BACKOFF)
            time.sleep(_BACKOFF)
    return []


def _upsert_parquet(path: Path, new_df: pd.DataFrame, pk: list[str]) -> None:
    """Append new_df to path, deduplicating on pk. Never deletes existing rows."""
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


def ingest_stations() -> None:
    """Fetch station coordinates and upsert into weather_stations.parquet."""
    codes_str = ",".join(_STATION_CODES)
    log.info("Fetching station coordinates ...")
    rows = _get(
        "f_kliima_jaam_vaatlus",
        [
            ("jaam_kood", f"in.({codes_str})"),
            ("jaam_periood_lopp", "eq.3999-12-31T23:59:00"),
        ],
    )
    if not rows:
        rows = _get("f_kliima_jaam_vaatlus", [("jaam_kood", f"in.({codes_str})")])

    if not rows:
        log.warning("No station coordinates returned")
        return

    df = pd.DataFrame(rows)
    df["_ingested_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    _upsert_parquet(
        _STAGING / "weather_stations.parquet",
        df,
        pk=["jaam_kood"],
    )


def ingest_observations(year: int, month: int) -> None:
    """Fetch hourly observations and upsert into weather_raw_YYYY_MM.parquet."""
    codes_str    = ",".join(_STATION_CODES)
    elements_str = ",".join(_ELEMENT_CODES)
    log.info("Fetching f_kliima_tund for %d-%02d ...", year, month)
    rows = _get(
        "f_kliima_tund",
        [
            ("aasta",        f"eq.{year}"),
            ("kuu",          f"eq.{month}"),
            ("jaam_kood",    f"in.({codes_str})"),
            ("element_kood", f"in.({elements_str})"),
        ],
    )
    log.info("Received %d raw rows", len(rows))
    if not rows:
        log.warning("No observations for %d-%02d", year, month)
        return

    df = pd.DataFrame(rows)
    df["_ingested_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    _upsert_parquet(
        _STAGING / f"weather_raw_{year}_{month:02d}.parquet",
        df,
        pk=["jaam_kood", "aasta", "kuu", "paev", "tund", "element_kood"],
    )


def main() -> None:
    # Accepts either:
    #   python ingest_weather.py 2025 12              (single month)
    #   python ingest_weather.py 2025 1 2025 12       (inclusive range)
    if len(sys.argv) == 3:
        y1, m1 = int(sys.argv[1]), int(sys.argv[2])
        y2, m2 = y1, m1
    elif len(sys.argv) == 5:
        y1, m1, y2, m2 = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
    else:
        print("Usage: python ingest_weather.py <year> <month> [year_end month_end]",
              file=sys.stderr)
        sys.exit(1)

    _STAGING.mkdir(parents=True, exist_ok=True)
    ingest_stations()

    y, m = y1, m1
    while (y, m) <= (y2, m2):
        ingest_observations(y, m)
        m += 1
        if m > 12:
            m, y = 1, y + 1


if __name__ == "__main__":
    main()
