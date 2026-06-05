import pandas as pd

df = pd.read_parquet("data/mart/mart_aq.parquet")

tartu = df[df["station_id"] == 8].copy()

tartu["month"] = tartu["obs_time"].dt.to_period("M")

monthly_pm10 = (
    tartu.groupby("month")["PM10"]
    .mean()
    .sort_values(ascending=False)
)

print(monthly_pm10)