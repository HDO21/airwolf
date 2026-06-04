import pandas as pd
from sqlalchemy import create_engine

# ⚠️ Muuda need enda andmebaasi järgi
engine = create_engine("postgresql://airflow:airflow@localhost:5432/airflow")

df = pd.read_parquet("data/mart/mart_joined.parquet")

df.to_sql("analysis_base", engine, if_exists="replace", index=False)

print("analysis_base loaded!")
