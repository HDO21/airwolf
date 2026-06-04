"""
ingestion/ — Airflow/andmebaasi sissevõtupakett
================================================
See pakett sisaldab andmebaasiühendusega sissevõtumooduleid, mida kasutab
Airflow DAG (dags/airwolf_pipeline.py). Iga moodul pakub funktsioone
`load_*_backfill()` ja `load_*_recent()`, mis võtavad vastu Airflow
PostgresHook'i ja kirjutavad andmed otse analytics-db staging-skeemi.

Lokaalse arenduse jaoks (ilma Dockeri/Airflow'ta) kasuta projekti juurkaustas
olevaid skripte:
    ingest_weather.py   — kirjutab toorandmed parquet-formaadis data/staging/
    ingest_air_quality.py
    ingest_traffic.py
Need sõltuvad: run_transform.py → run_mart.py → streamlit_app.py
"""
