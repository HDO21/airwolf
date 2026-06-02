from pathlib import Path
import pandas as pd

_DATA_DIR = Path("data")
_MART = _DATA_DIR / "mart"

aq = pd.read_parquet(_MART / "mart_aq.parquet")
weather = pd.read_parquet(_MART / "mart_weather.parquet")
traffic = pd.read_parquet(_MART / "mart_traffic.parquet")

# Ühenda kõik kolm linna üheks tabeliks
aq["obs_time"] = pd.to_datetime(aq["obs_time"])
weather["obs_time"] = pd.to_datetime(weather["obs_time"])
traffic["obs_time"] = pd.to_datetime(traffic["obs_time"])

merged = (
    aq
    .merge(weather, on=["obs_time", "area"], how="inner", suffixes=("_aq", "_w"))
    .merge(traffic, on=["obs_time", "area"], how="inner")
)

merged = merged[[
    "obs_time", "area",
    "SO2", "NO2", "O3", "PM10", "PM25",
    "temperature_c", "wind_speed_ms", "precip_mm",
    "total_flow"
]].dropna()

print("Ridu ühendatud tabelis:", len(merged))
print(merged.head())
print("\nLinnade jaotus:")
print(merged["area"].value_counts())

# --- Kõige puhtamad ja kõige saastatumad tunnid PM10 järgi ---

cleanest = (
    merged.sort_values("PM10")
    .groupby("area")
    .head(10)
)

dirtiest = (
    merged.sort_values("PM10", ascending=False)
    .groupby("area")
    .head(10)
)

print("\nKõige puhtamad tunnid (PM10):")
print(cleanest[[
    "obs_time", "area", "PM10",
    "temperature_c", "wind_speed_ms", "precip_mm", "total_flow"
]])

print("\nKõige saastatumad tunnid (PM10):")
print(dirtiest[[
    "obs_time", "area", "PM10",
    "temperature_c", "wind_speed_ms", "precip_mm", "total_flow"
]])
