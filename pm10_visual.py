import pandas as pd
import matplotlib.pyplot as plt

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

# Pane ühte tabelisse
combined = pd.DataFrame({
    "Tartu_PM10": tartu_monthly,
    "Tallinn_PM10": tallinn_monthly,
    "Narva_PM10": narva_monthly
})

# Joonista graafik
combined.plot(figsize=(12,6))
plt.title("PM10 kuude keskmised — Tartu vs Tallinn vs Narva")
plt.ylabel("PM10 (µg/m³)")
plt.xlabel("Kuu")
plt.grid(True)
plt.show()
