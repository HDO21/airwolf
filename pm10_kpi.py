import pandas as pd

# Loe andmed
df = pd.read_parquet("data/mart/mart_aq.parquet")

# Lisa kuu veerg
df["month"] = df["obs_time"].dt.to_period("M")

# Filtreeri linnad
tartu = df[df["station_id"] == 8].copy()
tallinn = df[df["station_id"] == 5].copy()
narva = df[df["station_id"] == 4].copy()

# Arvuta kuude keskmised
tartu_monthly = tartu.groupby("month")["PM10"].mean()
tallinn_monthly = tallinn.groupby("month")["PM10"].mean()
narva_monthly = narva.groupby("month")["PM10"].mean()

# KPI-d
tartu_max_month = tartu_monthly.idxmax()
tartu_max_value = tartu_monthly.max()

tallinn_max_month = tallinn_monthly.idxmax()
tallinn_max_value = tallinn_monthly.max()

narva_max_month = narva_monthly.idxmax()
narva_max_value = narva_monthly.max()

print("\n--- PM10 KPI-d ---")
print(f"Tartu kõige saastatum kuu:   {tartu_max_month} → {tartu_max_value:.2f} µg/m³")
print(f"Tallinna kõige saastatum kuu: {tallinn_max_month} → {tallinn_max_value:.2f} µg/m³")
print(f"Narva kõige saastatum kuu:    {narva_max_month} → {narva_max_value:.2f} µg/m³")

print("\n--- Erinevused µg/m³ ---")
print(f"Tallinn - Tartu: {tallinn_max_value - tartu_max_value:.2f}")
print(f"Tallinn - Narva: {tallinn_max_value - narva_max_value:.2f}")
print(f"Tartu - Narva:   {tartu_max_value - narva_max_value:.2f}")
