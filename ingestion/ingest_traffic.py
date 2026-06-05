#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import json
import time
import urllib3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import requests
from pyproj import Transformer

try:
    from psycopg2.extras import execute_values
except ModuleNotFoundError:  # Allows local linting/testing outside the Airflow image.
    execute_values = None

log = logging.getLogger(__name__)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ARCGIS_BASE = "https://tarktee.mnt.ee/tarktee/rest/services/traffic_detectors/MapServer/0"
HEADERS = {"Accept": "application/json"}
TIMEOUT = 30
MAX_RETRIES = 3
BACKOFF = 5
MAX_RECORDS = 1000
CSV_CHUNK_SIZE = 50_000

STUDY_AREAS: dict[str, dict[str, int]] = {
    "tallinn": {"x_min": 526818, "x_max": 557609, "y_min": 6580812, "y_max": 6601992},
    "narva": {"x_min": 732765, "x_max": 739464, "y_min": 6585793, "y_max": 6591660},
    "tartu": {"x_min": 643432, "x_max": 663197, "y_min": 6459800, "y_max": 6478907},
}

LIVE_FIELDS = ",".join(
    [
        "traffic_detector_id",
        "site_name",
        "road_name",
        "measurement_time",
        "total_flow_forwards",
        "total_flow_backwards",
        "heavy_traffic_forwards",
        "heavy_traffic_backwards",
        "average_speed_forwards",
        "average_speed_backwards",
        "relative_speed_forwards",
        "relative_speed_backwards",
    ]
)

wgs84_to_3301 = Transformer.from_crs("EPSG:4326", "EPSG:3301", always_xy=True)
_3301_to_wgs84 = Transformer.from_crs("EPSG:3301", "EPSG:4326", always_xy=True)

CSV_COLUMN_MAP = {
    "1": "motorcycle_count",
    "2": "car_light_van_count",
    "3": "car_light_van_trailer_count",
    "4": "heavy_van_count",
    "5": "light_goods_count",
    "6": "rigid_count",
    "7": "rigid_trailer_count",
    "8": "articulated_hgv_count",
    "9": "minibus_count",
    "10": "bus_coach_count",
    "<40Kph": "speed_lt_40_count",
    "40-<50": "speed_40_50_count",
    "50-<60": "speed_50_60_count",
    "60-<70": "speed_60_70_count",
    "70-<80": "speed_70_80_count",
    "80-<90": "speed_80_90_count",
    "90-<100": "speed_90_100_count",
    "100-<110": "speed_100_110_count",
    "110-<120": "speed_110_120_count",
    "120-<130": "speed_120_130_count",
    "=>130": "speed_gte_130_count",
}

COUNT_COLUMNS = list(CSV_COLUMN_MAP.values())

TRAFFIC_COUNTS_COLUMNS = [
    "run_id",
    "id",
    "kanal",
    "aeg",
    "site_name",
    "road_name",
    "area",
    "lat",
    "lon",
    "x_3301",
    "y_3301",
    *COUNT_COLUMNS,
    "source_file",
]

TRAFFIC_LIVE_COLUMNS = [
    "run_id",
    "traffic_detector_id",
    "measurement_time",
    "site_name",
    "road_name",
    "area",
    "lat",
    "lon",
    "x_3301",
    "y_3301",
    "total_flow_forwards",
    "total_flow_backwards",
    "heavy_traffic_forwards",
    "heavy_traffic_backwards",
    "average_speed_forwards",
    "average_speed_backwards",
    "relative_speed_forwards",
    "relative_speed_backwards",
]


def _none_if_nan(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return None
        return value.to_pydatetime()
    return value


def _to_int(value: Any) -> int | None:
    value = _none_if_nan(value)
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    value = _none_if_nan(value)
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _arcgis_time_to_datetime(value: Any) -> datetime | None:
    value = _none_if_nan(value)
    if value is None or value == "":
        return None

    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    try:
        number = float(value)
        # ArcGIS date fields are usually Unix epoch milliseconds.
        if number > 10_000_000_000:
            return datetime.fromtimestamp(number / 1000, tz=timezone.utc)
        return datetime.fromtimestamp(number, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        parsed = pd.to_datetime(value, errors="coerce", utc=True)
        if pd.isna(parsed):
            return None
        return parsed.to_pydatetime()


def _query_arcgis(params: dict[str, Any]) -> dict[str, Any]:
    url = f"{ARCGIS_BASE}/query"
    base = {"f": "json", "outSR": "3301", "returnGeometry": "true"}
    base.update(params)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(
                url,
                params=base,
                headers=HEADERS,
                timeout=TIMEOUT,
                verify=False,
        )
            if resp.status_code >= 500:
                raise requests.HTTPError(response=resp)
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                raise RuntimeError(f"ArcGIS API error: {data['error']}")
            return data
        except (requests.HTTPError, requests.ConnectionError, requests.Timeout, RuntimeError) as exc:
            if attempt == MAX_RETRIES:
                raise
            log.warning("Attempt %d/%d failed: %s — retrying in %ds", attempt, MAX_RETRIES, exc, BACKOFF)
            time.sleep(BACKOFF)

    return {}


def _find_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    normalized = {str(col).strip().lower(): col for col in df.columns}
    for candidate in candidates:
        found = normalized.get(candidate.strip().lower())
        if found is not None:
            return found
    return None

def _read_csv_flexible(path: Path, **kwargs) -> pd.DataFrame:
    """
    Loeb CSV faili erinevate kodeeringute ja eraldajatega.
    Valib variandi, kus tekib kõige rohkem veerge.
    """
    encodings = ["utf-8-sig", "utf-8", "cp1252", "latin1", "cp1257"]
    separators = [",", ";", "\t"]

    best_df: pd.DataFrame | None = None
    best_score = -1
    last_error: Exception | None = None

    for encoding in encodings:
        for sep in separators:
            try:
                df = pd.read_csv(
                    path,
                    encoding=encoding,
                    sep=sep,
                    engine="python",
                    quotechar='"',
                    doublequote=True,
                    on_bad_lines="warn",
                    **kwargs,
                )

                # Vali variant, kus päis parsiti kõige paremini.
                score = len(df.columns)

                if score > best_score:
                    best_df = df
                    best_score = score

                # Kui leidsime ID, Lat ja Lon veerud, on see kindlasti õige.
                normalized_cols = {str(c).strip().lower() for c in df.columns}
                if {"id", "lat", "lon"}.issubset(normalized_cols):
                    return df

            except Exception as exc:
                last_error = exc

    if best_df is not None and best_score > 1:
        return best_df

    if last_error is not None:
        raise last_error

    raise ValueError(f"Could not read CSV file: {path}")

def _load_station_lookup(stations_file: Path | None) -> dict[str, dict[str, Any]]:
    """Loads traffic detector metadata, if a station file is provided.

    Expected common columns: ID/id, Lat/lat, Lon/lon, Nimetus/site_name, Tee nimi/road_name.
    The function is intentionally permissive because the portal files may be CSV or Excel.
    """
    if stations_file is None:
        return {}
    if not stations_file.exists():
        raise FileNotFoundError(f"Traffic station file not found: {stations_file}")

    if stations_file.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(stations_file, dtype=str)
    else:
        df = _read_csv_flexible(stations_file, dtype=str)

    df.columns = [str(col).strip() for col in df.columns]

    id_col = _find_column(df, ["ID", "id", "loendusseadme id", "loenduri id", "traffic_detector_id"])
    lat_col = _find_column(df, ["Lat", "lat", "latitude", "laius", "laiuskraad", "y_wgs84"])
    lon_col = _find_column(df, ["Lon", "lon", "longitude", "pikkus", "pikkuskraad", "x_wgs84"])
    x_col = _find_column(df, ["x_3301", "X_3301", "x", "X", "l_est_x", "L-EST X"])
    y_col = _find_column(df, ["y_3301", "Y_3301", "y", "Y", "l_est_y", "L-EST Y"])
    name_col = _find_column(df, ["Nimetus", "nimetus", "site_name", "name", "nimi", "jaam", "jaama_nimi"])
    road_col = _find_column(df, ["Tee nimi", "tee_nimi", "road_name", "tee", "road", "maantee", "tänav"])

    if id_col is None:
        raise ValueError(f"Could not find detector ID column in {stations_file}. Columns: {list(df.columns)}")

    if lat_col is not None:
        df[lat_col] = pd.to_numeric(df[lat_col].str.replace(",", ".", regex=False), errors="coerce")
    if lon_col is not None:
        df[lon_col] = pd.to_numeric(df[lon_col].str.replace(",", ".", regex=False), errors="coerce")
    if x_col is not None:
        df[x_col] = pd.to_numeric(df[x_col].str.replace(",", ".", regex=False), errors="coerce")
    if y_col is not None:
        df[y_col] = pd.to_numeric(df[y_col].str.replace(",", ".", regex=False), errors="coerce")

    lookup: dict[str, dict[str, Any]] = {}

    for _, row in df.iterrows():
        detector_id = _none_if_nan(row.get(id_col))
        if detector_id is None:
            continue
        detector_id = str(detector_id).strip()

        lat = _to_float(row.get(lat_col)) if lat_col is not None else None
        lon = _to_float(row.get(lon_col)) if lon_col is not None else None
        x_3301 = _to_float(row.get(x_col)) if x_col is not None else None
        y_3301 = _to_float(row.get(y_col)) if y_col is not None else None
        area = None

        # Prefer explicit lat/lon when present. If only EPSG:3301 coordinates are present, convert them.
        if lat is not None and lon is not None and (x_3301 is None or y_3301 is None):
            x_3301, y_3301 = wgs84_to_3301.transform(lon, lat)
        elif (lat is None or lon is None) and x_3301 is not None and y_3301 is not None:
            lon, lat = _3301_to_wgs84.transform(x_3301, y_3301)

        if x_3301 is not None and y_3301 is not None:
            for name, bb in STUDY_AREAS.items():
                if bb["x_min"] <= x_3301 <= bb["x_max"] and bb["y_min"] <= y_3301 <= bb["y_max"]:
                    area = name
                    break

        lookup[detector_id] = {
            "site_name": _none_if_nan(row.get(name_col)) if name_col is not None else None,
            "road_name": _none_if_nan(row.get(road_col)) if road_col is not None else None,
            "area": area,
            "lat": lat,
            "lon": lon,
            "x_3301": x_3301,
            "y_3301": y_3301,
        }

    log.info("Loaded %d traffic detector metadata rows from %s", len(lookup), stations_file)
    return lookup


def _resolve_csv_paths(csv_paths: str | Path | Iterable[str | Path]) -> list[Path]:
    if isinstance(csv_paths, (str, Path)):
        raw = str(csv_paths).strip()
        if not raw:
            return []

        # Accept comma/semicolon-separated paths from Airflow params.
        parts = [part.strip() for part in raw.replace(";", ",").split(",") if part.strip()]
    else:
        parts = [str(path).strip() for path in csv_paths if str(path).strip()]

    resolved: list[Path] = []
    for part in parts:
        path = Path(part)
        if path.is_dir():
            resolved.extend(sorted(path.glob("*.csv")))
        else:
            resolved.append(path)

    return resolved


def _prepare_counts_chunk(
    df: pd.DataFrame,
    run_id: str,
    source_file: str,
    station_lookup: dict[str, dict[str, Any]],
) -> list[tuple]:
    required = {"id", "kanal", "aeg"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Traffic CSV is missing required columns: {sorted(missing)}. Available columns: {list(df.columns)}")

    df = df.copy()
    df["id"] = df["id"].astype(str).str.strip()
    df["kanal"] = pd.to_numeric(df["kanal"], errors="coerce").astype("Int64")
    df["aeg"] = pd.to_datetime(df["aeg"], format="%Y-%m-%d %H:%M:%S", errors="coerce")

    for csv_col, out_col in CSV_COLUMN_MAP.items():
        if csv_col in df.columns:
            df[out_col] = pd.to_numeric(df[csv_col], errors="coerce").astype("Int64")
        else:
            df[out_col] = pd.NA

    df = df.dropna(subset=["id", "kanal", "aeg"])

    rows: list[tuple] = []
    for record in df.to_dict(orient="records"):
        detector_id = str(record.get("id")).strip()
        station = station_lookup.get(detector_id, {})

        if station.get("area") not in {"tallinn", "tartu", "narva"}:
            continue

        row = {
            "run_id": run_id,
            "id": detector_id,
            "kanal": _to_int(record.get("kanal")),
            "aeg": _none_if_nan(record.get("aeg")),
            "site_name": station.get("site_name"),
            "road_name": station.get("road_name"),
            "area": station.get("area"),
            "lat": station.get("lat"),
            "lon": station.get("lon"),
            "x_3301": station.get("x_3301"),
            "y_3301": station.get("y_3301"),
            **{col: _to_int(record.get(col)) for col in COUNT_COLUMNS},
            "source_file": source_file,
        }
        rows.append(tuple(row[col] for col in TRAFFIC_COUNTS_COLUMNS))

    return rows


def _upsert_traffic_counts_rows(hook, rows: list[tuple], schema: str = "staging") -> int:
    if not rows:
        return 0

    columns_sql = ", ".join(TRAFFIC_COUNTS_COLUMNS) + ", loaded_at"
    placeholders = ", ".join(["%s"] * len(TRAFFIC_COUNTS_COLUMNS))

    update_columns = [col for col in TRAFFIC_COUNTS_COLUMNS if col not in {"id", "kanal", "aeg"}]
    update_sql = ",\n            ".join([f"{col} = EXCLUDED.{col}" for col in update_columns])

    sql = f"""
        INSERT INTO {schema}.traffic_counts_raw
            ({columns_sql})
        VALUES ({placeholders}, NOW())
        ON CONFLICT (id, kanal, aeg) DO UPDATE SET
            {update_sql},
            loaded_at = NOW()
    """

    with closing(hook.get_conn()) as conn:
        with conn:
            with conn.cursor() as cur:
                if execute_values is not None:
                    values_sql = sql.replace(f"VALUES ({placeholders}, NOW())", "VALUES %s")
                    template = "(" + ", ".join(["%s"] * len(TRAFFIC_COUNTS_COLUMNS)) + ", NOW())"
                    execute_values(cur, values_sql, rows, template=template, page_size=5000)
                else:
                    cur.executemany(sql, rows)

    return len(rows)


def load_traffic_counts_backfill(
    hook,
    run_id: str,
    csv_paths: str | Path | Iterable[str | Path],
    stations_file: str | Path | None = None,
    schema: str = "staging",
    chunksize: int = CSV_CHUNK_SIZE,
) -> int:
    """Loads historical traffic count CSV files into staging.traffic_counts_raw.

    The CSV source has the original columns id, kanal, aeg, vehicle classes 1-10,
    and speed buckets. This function keeps id/kanal/aeg close to the source and
    maps numeric/symbolic count columns to SQL-safe names.
    """
    paths = _resolve_csv_paths(csv_paths)
    if not paths:
        log.info("No traffic CSV backfill paths provided; skipping traffic counts backfill")
        return 0

    for path in paths:
        if not path.exists():
            raise FileNotFoundError(f"Traffic CSV file not found: {path}")

    station_lookup = _load_station_lookup(Path(stations_file) if stations_file else None)

    total_upserted = 0
    for path in paths:
        log.info("Loading traffic counts CSV: %s", path)
        for chunk in pd.read_csv(path, dtype=str, chunksize=chunksize):
            rows = _prepare_counts_chunk(
                df=chunk,
                run_id=run_id,
                source_file=path.name,
                station_lookup=station_lookup,
            )
            upserted = _upsert_traffic_counts_rows(hook=hook, rows=rows, schema=schema)
            total_upserted += upserted
            log.info("Upserted %d traffic count rows from %s; total=%d", upserted, path.name, total_upserted)

    log.info("Traffic counts backfill upserted %d rows in total", total_upserted)
    return total_upserted


def _prepare_live_row(raw: dict[str, Any], area_name: str) -> tuple | None:
    detector_id = _none_if_nan(raw.get("traffic_detector_id"))
    measurement_time = _arcgis_time_to_datetime(raw.get("measurement_time"))

    if detector_id is None or measurement_time is None:
        return None

    x_3301 = _to_float(raw.get("x_3301"))
    y_3301 = _to_float(raw.get("y_3301"))
    lat = None
    lon = None

    if x_3301 is not None and y_3301 is not None:
        lon, lat = _3301_to_wgs84.transform(x_3301, y_3301)

    row = {
        "traffic_detector_id": str(detector_id).strip(),
        "measurement_time": measurement_time,
        "site_name": _none_if_nan(raw.get("site_name")),
        "road_name": _none_if_nan(raw.get("road_name")),
        "area": area_name,
        "lat": lat,
        "lon": lon,
        "x_3301": x_3301,
        "y_3301": y_3301,
        "total_flow_forwards": _to_int(raw.get("total_flow_forwards")),
        "total_flow_backwards": _to_int(raw.get("total_flow_backwards")),
        "heavy_traffic_forwards": _to_int(raw.get("heavy_traffic_forwards")),
        "heavy_traffic_backwards": _to_int(raw.get("heavy_traffic_backwards")),
        "average_speed_forwards": _to_float(raw.get("average_speed_forwards")),
        "average_speed_backwards": _to_float(raw.get("average_speed_backwards")),
        "relative_speed_forwards": _to_float(raw.get("relative_speed_forwards")),
        "relative_speed_backwards": _to_float(raw.get("relative_speed_backwards")),
    }

    return tuple(row[col] for col in TRAFFIC_LIVE_COLUMNS if col != "run_id")


def _upsert_traffic_live_rows(hook, run_id: str, rows_without_run_id: list[tuple], schema: str = "staging") -> int:
    if not rows_without_run_id:
        return 0

    rows = [(run_id, *row) for row in rows_without_run_id]
    columns_sql = ", ".join(TRAFFIC_LIVE_COLUMNS) + ", loaded_at"
    placeholders = ", ".join(["%s"] * len(TRAFFIC_LIVE_COLUMNS))

    update_columns = [col for col in TRAFFIC_LIVE_COLUMNS if col not in {"traffic_detector_id", "measurement_time"}]
    update_sql = ",\n            ".join([f"{col} = EXCLUDED.{col}" for col in update_columns])

    sql = f"""
        INSERT INTO {schema}.traffic_live_raw
            ({columns_sql})
        VALUES ({placeholders}, NOW())
        ON CONFLICT (traffic_detector_id, measurement_time) DO UPDATE SET
            {update_sql},
            loaded_at = NOW()
    """

    with closing(hook.get_conn()) as conn:
        with conn:
            with conn.cursor() as cur:
                if execute_values is not None:
                    values_sql = sql.replace(f"VALUES ({placeholders}, NOW())", "VALUES %s")
                    template = "(" + ", ".join(["%s"] * len(TRAFFIC_LIVE_COLUMNS)) + ", NOW())"
                    execute_values(cur, values_sql, rows, template=template, page_size=5000)
                else:
                    cur.executemany(sql, rows)

    return len(rows)


def load_traffic_live_recent(
    hook,
    run_id: str,
    schema: str = "staging",
) -> int:
    """Loads the latest Tark Tee traffic detector snapshot into staging.traffic_live_raw.

    The ArcGIS layer is treated as a current/live source. Running this task hourly
    appends or updates by traffic_detector_id + measurement_time.
    """
    all_rows: list[tuple] = []

    for area_name, bbox in STUDY_AREAS.items():
        geometry = f"{bbox['x_min']},{bbox['y_min']},{bbox['x_max']},{bbox['y_max']}"
        offset = 0

        while True:
            result = _query_arcgis(
                {
                    "where": "1=1",
                    "geometry": geometry,
                    "geometryType": "esriGeometryEnvelope",
                    "inSR": "3301",
                    "spatialRel": "esriSpatialRelIntersects",
                    "outFields": LIVE_FIELDS,
                    "resultOffset": offset,
                    "resultRecordCount": MAX_RECORDS,
                }
            )

            features = result.get("features", [])
            for feature in features:
                attributes = feature.get("attributes", {}) or {}
                geometry_data = feature.get("geometry") or {}
                raw = dict(attributes)
                raw["x_3301"] = geometry_data.get("x")
                raw["y_3301"] = geometry_data.get("y")
                raw["area"] = area_name

                row = _prepare_live_row(raw, area_name)
                if row is not None:
                    all_rows.append(row)

            if len(features) < MAX_RECORDS:
                break
            offset += MAX_RECORDS

    upserted = _upsert_traffic_live_rows(hook=hook, run_id=run_id, rows_without_run_id=all_rows, schema=schema)
    log.info("Traffic live load upserted %d rows", upserted)
    return upserted


# Backwards-compatible aliases, if an older DAG imports these names.
def load_traffic_backfill(*args, **kwargs) -> int:
    return load_traffic_counts_backfill(*args, **kwargs)


def load_traffic_live(*args, **kwargs) -> int:
    return load_traffic_live_recent(*args, **kwargs)


def main() -> None:
    parser = argparse.ArgumentParser(description="Load traffic data into PostgreSQL staging tables")
    parser.add_argument("--mode", choices=["counts-backfill", "live"], required=True)
    parser.add_argument("--csv-paths", help="CSV path, directory, or comma-separated paths for counts backfill")
    parser.add_argument("--stations-file", type=Path, help="Optional detector metadata CSV/XLSX file")
    args = parser.parse_args()

    raise SystemExit(
        "This module is intended to be called by Airflow with a PostgresHook. "
        "Use load_traffic_counts_backfill(...) or load_traffic_live_recent(...)."
    )


if __name__ == "__main__":
    main()
