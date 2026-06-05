"""Shared validation module for all ingestion scripts.

Usage:
    from validate import validate
    result = validate(df, "weather")   # returns {"passed": bool, "issues": [...]}
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)

_REQUIRED_COLS: dict[str, list[str]] = {
    "weather": ["station_id", "obs_time", "lat", "lon"],
    "air_quality": ["station_id", "obs_time", "lat", "lon", "area"],
    "traffic_live": ["traffic_detector_id", "measurement_time", "x_3301", "y_3301"],
    "traffic_backfill": ["id", "aeg"],
}

# For air quality sourced from ohuseire.ee, all four pollutants are expected
# because stations with missing indicators are excluded at ingest time.
_AQ_POLLUTANTS = ["O3", "NO2", "SO2", "PM10", "PM25"]
_AQ_MAX_NULL_PCT = 5.0   # hard-fail threshold per pollutant column


def validate(df: pd.DataFrame, schema_name: str) -> dict[str, Any]:
    """Run validation checks and return {"passed": bool, "issues": list[str]}.

    Marks passed=False if any required column is missing or has >5% null values.
    Other checks (range, at-least-one) append issues but do not fail the run.
    """
    issues: list[str] = []
    total = len(df)
    hard_fail = False

    required = _REQUIRED_COLS.get(schema_name, [])

    for col in required:
        if col not in df.columns:
            issues.append(f"Missing required column: {col}")
            hard_fail = True
            continue
        null_count = int(df[col].isna().sum())
        if null_count:
            pct = null_count / total * 100 if total else 0.0
            issues.append(f"{col}: {null_count} nulls ({pct:.1f}%)")
            if pct > 5:
                hard_fail = True

    if schema_name == "weather":
        _at_least_one(df, ["temperature_c", "wind_speed_ms", "precip_mm"], issues)
        _check_range(df, "lat", 57.0, 60.5, issues)
        _check_range(df, "lon", 21.0, 29.0, issues)
        _check_gte(df, "wind_speed_ms", 0.0, issues)
        _check_range(df, "temperature_c", -50.0, 50.0, issues)
        _check_gte(df, "precip_mm", 0.0, issues)

    elif schema_name == "air_quality":
        # Every row must have at least one reading (belt-and-suspenders guard)
        _at_least_one(df, _AQ_POLLUTANTS, issues)
        # Each pollutant column is individually required: stations are pre-filtered
        # to include only those that measure all four indicators.
        for col in _AQ_POLLUTANTS:
            if col not in df.columns:
                issues.append(f"Missing pollutant column: {col}")
                hard_fail = True
                continue
            null_count = int(df[col].isna().sum())
            if null_count:
                pct = null_count / total * 100 if total else 0.0
                issues.append(f"{col}: {null_count} nulls ({pct:.1f}%)")
                if pct > _AQ_MAX_NULL_PCT:
                    hard_fail = True
            _check_gte(df, col, 0.0, issues)
        _check_range(df, "lat", 57.0, 60.5, issues)
        _check_range(df, "lon", 21.0, 29.0, issues)

    elif schema_name == "traffic_live":
        _check_gte(df, "total_flow_forwards", 0.0, issues)
        _check_gte(df, "total_flow_backwards", 0.0, issues)
        _check_range(df, "x_3301", 300_000.0, 800_000.0, issues)
        _check_range(df, "y_3301", 6_375_000.0, 6_750_000.0, issues)

    elif schema_name == "traffic_backfill":
        _check_gte(df, "total_flow", 0.0, issues)
        _check_range(df, "heavy_vehicle_share", 0.0, 1.0, issues)

    # Print summary
    present_required = [c for c in required if c in df.columns]
    null_counts = {c: int(df[c].isna().sum()) for c in present_required}
    print(f"\n[validate:{schema_name}]  total_rows={total}")
    for col, n in null_counts.items():
        print(f"  {col}: {n} nulls")
    if issues:
        for iss in issues:
            print(f"  ISSUE: {iss}")
    else:
        print("  all checks passed")

    return {"passed": not hard_fail, "issues": issues}


def _at_least_one(df: pd.DataFrame, cols: list[str], issues: list[str]) -> None:
    present = [c for c in cols if c in df.columns]
    if not present:
        return
    count = int(df[present].isna().all(axis=1).sum())
    if count:
        issues.append(f"rows where all of {present} are null: {count}")


def _check_range(df: pd.DataFrame, col: str, lo: float, hi: float, issues: list[str]) -> None:
    if col not in df.columns:
        return
    s = pd.to_numeric(df[col], errors="coerce").dropna()
    out = int(((s < lo) | (s > hi)).sum())
    if out:
        issues.append(f"{col}: {out} value(s) outside [{lo}, {hi}]")


def _check_gte(df: pd.DataFrame, col: str, threshold: float, issues: list[str]) -> None:
    if col not in df.columns:
        return
    s = pd.to_numeric(df[col], errors="coerce").dropna()
    out = int((s < threshold).sum())
    if out:
        issues.append(f"{col}: {out} value(s) below {threshold}")
