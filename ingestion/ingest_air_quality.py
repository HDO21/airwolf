#!/usr/bin/env python3
from __future__ import annotations

import calendar
import datetime as dt
import logging
import sys
import time
from typing import Any

import requests

from ingestion.db import get_conn, insert_pipeline_run, upsert_rows

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

BASE_URL = "https://ohuseire.ee/api/monitoring/et"
HEADERS = {"Accept": "application/json"}
TIMEOUT = 30
MAX_RETRIES = 3
BACKOFF = 5

STATION_IDS = [4, 5, 7, 8]               # Narva, Liivalaia, Õismäe, Tartu
INDICATOR_IDS = [1, 3, 6, 21, 23]        # SO2, NO2, O3, PM10, PM25


def _get(params: dict[str, Any]) -> list[dict[str, Any]]:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=TIMEOUT)
            if resp.status_code >= 500:
                raise requests.HTTPError(response=resp)
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else []
        except (requests.HTTPError, requests.ConnectionError, requests.Timeout) as exc:
            if attempt == MAX_RETRIES:
                raise
            log.warning("Attempt %d/%d failed: %s — retrying in %ds", attempt, MAX_RETRIES, exc, BACKOFF)
            time.sleep(BACKOFF)
    return []


def _to_text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def ingest_month(year: int, month: int) -> int:
    last_day = calendar.monthrange(year, month)[1]
    range_str = f"01.{month:02d}.{year},{last_day:02d}.{month:02d}.{year}"
    rows = _get({
        "indicators": ",".join(map(str, INDICATOR_IDS)),
        "range": range_str,
        "resolution": "+",
        "stations": ",".join(map(str, STATION_IDS)),
        "type": "INDICATOR",
    })
    if not rows:
        log.warning("No air-quality data returned for %d-%02d", year, month)
        return 0

    run_id = f"air_quality_{year}_{month:02d}_{dt.datetime.now(dt.UTC).strftime('%Y%m%dT%H%M%SZ')}"
    out = []
    for r in rows:
        out.append({
            "station": _to_text(r.get("station")),
            "indicator": _to_text(r.get("indicator")),
            "measured": r.get("measured"),
            "payload": r,
            "run_id": run_id,
        })

    with get_conn() as conn:
        insert_pipeline_run(conn, run_id, "air_quality", "running")
        count = upsert_rows(
            conn,
            "staging.air_quality_raw",
            out,
            ["station", "indicator", "measured", "payload", "run_id"],
            ["station", "indicator", "measured"],
        )
        insert_pipeline_run(conn, run_id, "air_quality", "success", f"Loaded {count} rows")
    log.info("Loaded %d air-quality rows for %d-%02d", count, year, month)
    return count


def main() -> None:
    if len(sys.argv) != 5:
        print("Usage: python ingest_air_quality.py <year_start> <month_start> <year_end> <month_end>", file=sys.stderr)
        sys.exit(1)
    y1, m1, y2, m2 = map(int, sys.argv[1:5])
    y, m = y1, m1
    while (y, m) <= (y2, m2):
        ingest_month(y, m)
        m += 1
        if m > 12:
            m, y = 1, y + 1


if __name__ == "__main__":
    main()
