from pathlib import Path
import pandas as pd

_DATA_DIR = Path("data")
_MART = _DATA_DIR / "mart"

aq = pd.read_parquet(_MART / "mart_aq.parquet")
weather = pd.read_parquet(_MART / "mart_weather.parquet")
traffic = pd.read_parquet(_MART / "mart_traffic.parquet")

# --- Filtreeri Tartu ---
aq_tartu = aq[aq["area"] == "tartu"].copy()
weather_tartu = weather[weather["area"] == "tartu"].copy()
traffic_tartu = traffic[traffic["area"] == "tartu"].copy()

# Ühtlusta ajad
aq_tartu["obs_time"] = pd.to_datetime(aq_tartu["obs_time"])
weather_tartu["obs_time"] = pd.to_datetime(weather_tartu["obs_time"])
traffic_tartu["obs_time"] = pd.to_datetime(traffic_tartu["obs_time"])

# --- Ühenda kõik üheks tabeliks ---
merged = (
    aq_tartu
    .merge(weather_tartu, on=["obs_time", "area"], how="inner", suffixes=("_aq", "_w"))
    .merge(traffic_tartu, on=["obs_time", "area"], how="inner")
)

# Hoia alles ainult vajalikud veerud
merged = merged[[
    "obs_time", "area",
    "SO2", "NO2", "O3", "PM10", "PM25",
    "temperature_c", "wind_speed_ms", "precip_mm",
    "total_flow"
]].dropna()

print("Ridu ühendatud tabelis:", len(merged))
print(merged.head())

# --- Korrelatsioonid Tartu kohta ---
corr = merged.corr(numeric_only=True)
print("\nKorrelatsioonimaatriks (Tartu):")
print(corr)
