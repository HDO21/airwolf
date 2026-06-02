import pandas as pd
df = pd.read_parquet("data/mart/dim_stations.parquet")
print(df.head())
