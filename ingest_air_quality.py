#!/usr/bin/env python3
"""Ingest raw air-quality observations from ohuseire.ee into data/staging/.

Preserves the API response with minimal modification. All normalisation,
indicator name mapping, spatial filtering and validation are done by
run_transform.py.

Staging files are never overwritten: new records are merged and deduplicated
by their natural primary key (station × indicator × measured).

Usage:
    python ingest_air_quality.py 2024 1 2025 12
"""
from __future__ import annotations

import calendar
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

_BASE_URL    = "https://ohuseire.ee/api/monitoring/et"
_HEADERS     = {"Accept": "application/json"}
_STAGING     = Path("data/staging")
_TIMEOUT     = 30
_MAX_RETRIES = 3
_BACKOFF     = 5

# All stations that measure all five target indicators (Rahu/6 excluded: no PM2.5)
_STATION_IDS  = [4, 5, 7, 8]   # Narva, Liivalaia, Õismäe, Tartu
_INDICATOR_IDS = [1, 3, 6, 21, 23]  # SO2, NO2, O3, PM10, PM25


def _get(params: dict[str, Any]) -> list[dict]:
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = requests.get(_BASE_URL, params=params, headers=_HEADERS, timeout=_TIMEOUT)
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


def ingest_month(year: int, month: int) -> None:
    last_day   = calendar.monthrange(year, month)[1]
    range_str  = f"01.{month:02d}.{year},{last_day:02d}.{month:02d}.{year}"
    stations_str   = ",".join(str(s) for s in _STATION_IDS)
    indicators_str = ",".join(str(i) for i in _INDICATOR_IDS)

    log.info("Fetching ohuseire.ee for %d-%02d ...", year, month)
    rows = _get({
        "indicators": indicators_str,
        "range":      range_str,
        "resolution": "+",
        "stations":   stations_str,
        "type":       "INDICATOR",
    })
    log.info("Received %d raw rows", len(rows))
    if not rows:
        log.warning("No data returned for %d-%02d", year, month)
        return

    df = pd.DataFrame(rows)
    df["_ingested_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    _upsert_parquet(
        _STAGING / f"air_quality_raw_{year}_{month:02d}.parquet",
        df,
        pk=["station", "indicator", "measured"],
    )


def main() -> None:
    if len(sys.argv) != 5:
        print("Usage: python ingest_air_quality.py "
              "<year_start> <month_start> <year_end> <month_end>", file=sys.stderr)
        sys.exit(1)

    y1, m1, y2, m2 = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
    _STAGING.mkdir(parents=True, exist_ok=True)

    y, m = y1, m1
    while (y, m) <= (y2, m2):
        ingest_month(y, m)
        m += 1
        if m > 12:
            m, y = 1, y + 1


if __name__ == "__main__":
    main()
