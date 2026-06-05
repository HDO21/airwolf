"""Ilmaandmete tunnisissevõtt — eraldiseisev DAG.

NB! See DAG täidab sama funktsiooni, mida airwolf_pipeline DAG (mis käsitleb
kõiki kolme andmeallikat koos). Ära luba mõlemat korraga.
"""
from airflow import DAG
from airflow.decorators import task
from airflow.providers.postgres.hooks.postgres import PostgresHook
from datetime import datetime, timedelta
import uuid

from ingestion.ingest_weather import load_weather_recent

default_args = {
    "owner": "airwolf",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="ingest_weather",
    start_date=datetime(2024, 1, 1),
    schedule="@hourly",
    catchup=False,
    is_paused_upon_creation=True,
    default_args=default_args,
    tags=["weather", "ingest"],
) as dag:

    @task
    def run_weather_ingest():
        hook = PostgresHook(postgres_conn_id="analytics_db")
        run_id = str(uuid.uuid4())
        # vali kas backfill või recent
        return load_weather_recent(hook=hook, run_id=run_id, lookback_hours=48)

    run_weather_ingest()