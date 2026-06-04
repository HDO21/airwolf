from __future__ import annotations

import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.append("/opt/airflow")

from airflow.sdk import DAG, Param
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.providers.standard.operators.bash import BashOperator

from ingestion.ingest_weather import load_weather_backfill, load_weather_recent
from ingestion.ingest_air_quality import load_air_quality_backfill, load_air_quality_recent
from ingestion.ingest_traffic import load_traffic_counts_backfill, load_traffic_live_recent

log = logging.getLogger(__name__)

POSTGRES_CONN_ID = "analytics_db"
SCHEMA_NAME = "staging"
CREATE_TABLES_SQL = Path("/opt/airflow/sql/create_tables.sql")
DBT_PROJECT_DIR = "/opt/airflow/dbt_project"


def _hook() -> PostgresHook:
    """Tagastab ühenduse analytics-db andmebaasi vastu."""
    return PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)


def create_tables() -> None:
    """Loob staging/intermediate/marts skeemid ja staging.*_raw tabelid."""
    if not CREATE_TABLES_SQL.exists():
        raise FileNotFoundError(f"SQL file not found: {CREATE_TABLES_SQL}")

    sql = CREATE_TABLES_SQL.read_text(encoding="utf-8")
    _hook().run(sql)


def _start_run(
    hook: PostgresHook,
    source_name: str,
    message: str | None = None,
) -> str:
    """Lisab staging.pipeline_runs tabelisse uue jooksu staatusega running."""
    run_id = str(uuid.uuid4())

    hook.run(
        """
        INSERT INTO staging.pipeline_runs
            (run_id, source_name, loaded_at, status, message)
        VALUES
            (%s, %s, NOW(), %s, %s)
        """,
        parameters=(run_id, source_name, "running", message),
    )

    return run_id


def _finish_run(
    hook: PostgresHook,
    run_id: str,
    status: str,
    message: str | None = None,
) -> None:
    """Uuendab pipeline_runs tabelis jooksu lõppstaatuse."""
    hook.run(
        """
        UPDATE staging.pipeline_runs
        SET status = %s,
            message = %s
        WHERE run_id = %s
        """,
        parameters=(status, message, run_id),
    )


def _period_from_params(context) -> tuple[int, int, int, int, datetime, datetime]:
    params = context["params"]

    year_start = int(params["year_start"])
    month_start = int(params["month_start"])
    year_end = int(params["year_end"])
    month_end = int(params["month_end"])

    period_start = datetime(year_start, month_start, 1, tzinfo=timezone.utc)

    if month_end == 12:
        period_end = datetime(year_end + 1, 1, 1, tzinfo=timezone.utc)
    else:
        period_end = datetime(year_end, month_end + 1, 1, tzinfo=timezone.utc)

    return year_start, month_start, year_end, month_end, period_start, period_end


def ingest_weather_backfill(**context) -> int:
    """
    Ilmaandmete backfill.

    Käivitub ainult siis, kui DAG trigger config'is on:
        {"run_weather_backfill": true}

    Vaikimisi periood on 2026 märts kuni 2026 mai, aga seda saab
    Airflow UI-s parameetritega muuta.
    """
    params = context["params"]
    run_backfill = bool(params.get("run_weather_backfill"))

    if not run_backfill:
        log.info("run_weather_backfill=false; skipping weather backfill")
        return 0

    hook = _hook()
    year_start, month_start, year_end, month_end, period_start, period_end = _period_from_params(context)

    run_id = _start_run(
        hook=hook,
        source_name="weather_backfill",
        message=f"Weather backfill {period_start.date()} to {period_end.date()}",
    )

    try:
        rows = load_weather_backfill(
            hook=hook,
            run_id=run_id,
            year_start=year_start,
            month_start=month_start,
            year_end=year_end,
            month_end=month_end,
            schema=SCHEMA_NAME,
        )
        _finish_run(hook, run_id, "success", f"Backfill upserted {rows} weather rows")
        return rows
    except Exception as exc:
        _finish_run(hook, run_id, "failed", str(exc))
        raise


def ingest_weather_hourly(**context) -> int:
    """
    Regulaarne ilmaandmete laadimine.

    Käib iga DAG run'iga ja laeb viimased N tundi uuesti.
    ON CONFLICT loogika ingest_weather.py failis väldib duplikaate.
    """
    params = context["params"]
    lookback_hours = int(params.get("weather_lookback_hours", 48))

    hook = _hook()
    run_id = _start_run(
        hook=hook,
        source_name="weather_hourly",
        message=f"Weather hourly load, lookback_hours={lookback_hours}",
    )

    try:
        rows = load_weather_recent(
            hook=hook,
            run_id=run_id,
            lookback_hours=lookback_hours,
            schema=SCHEMA_NAME,
        )
        _finish_run(hook, run_id, "success", f"Hourly load upserted {rows} weather rows")
        return rows
    except Exception as exc:
        _finish_run(hook, run_id, "failed", str(exc))
        raise


def ingest_air_quality_backfill(**context) -> int:
    """
    Õhukvaliteedi backfill.

    Käivitub ainult siis, kui DAG trigger config'is on:
        {"run_air_quality_backfill": true}

    Vaikimisi periood on 2026 märts kuni 2026 mai, aga seda saab
    Airflow UI-s parameetritega muuta.
    """
    params = context["params"]
    run_backfill = bool(params.get("run_air_quality_backfill"))

    if not run_backfill:
        log.info("run_air_quality_backfill=false; skipping air quality backfill")
        return 0

    hook = _hook()
    year_start, month_start, year_end, month_end, period_start, period_end = _period_from_params(context)

    run_id = _start_run(
        hook=hook,
        source_name="air_quality_backfill",
        message=f"Air quality backfill {period_start.date()} to {period_end.date()}",
    )

    try:
        rows = load_air_quality_backfill(
            hook=hook,
            run_id=run_id,
            year_start=year_start,
            month_start=month_start,
            year_end=year_end,
            month_end=month_end,
            schema=SCHEMA_NAME,
        )
        _finish_run(hook, run_id, "success", f"Backfill upserted {rows} air quality rows")
        return rows
    except Exception as exc:
        _finish_run(hook, run_id, "failed", str(exc))
        raise


def ingest_air_quality_hourly(**context) -> int:
    """
    Regulaarne õhukvaliteedi laadimine.

    Käib iga DAG run'iga ja laeb viimased N tundi uuesti.
    ON CONFLICT loogika ingest_air_quality.py failis väldib duplikaate.
    """
    params = context["params"]
    lookback_hours = int(params.get("air_quality_lookback_hours", 48))

    hook = _hook()
    run_id = _start_run(
        hook=hook,
        source_name="air_quality_hourly",
        message=f"Air quality hourly load, lookback_hours={lookback_hours}",
    )

    try:
        rows = load_air_quality_recent(
            hook=hook,
            run_id=run_id,
            lookback_hours=lookback_hours,
            schema=SCHEMA_NAME,
        )
        _finish_run(hook, run_id, "success", f"Hourly load upserted {rows} air quality rows")
        return rows
    except Exception as exc:
        _finish_run(hook, run_id, "failed", str(exc))
        raise


def ingest_traffic_counts_backfill(**context) -> int:
    """
    Liiklusloenduse CSV backfill.

    Käivitub ainult siis, kui DAG trigger config'is on:
        {"run_traffic_counts_backfill": true}

    traffic_counts_files võib olla:
      - üks CSV fail
      - kaust, kus on traffic_2025.csv / traffic_2026.csv failid
      - komaga eraldatud failide nimekiri

    traffic_stations_file on LL_jaamad.csv, kust võetakse jaama nimi/asukoht.
    """
    params = context["params"]
    run_backfill = bool(params.get("run_traffic_counts_backfill"))

    if not run_backfill:
        log.info("run_traffic_counts_backfill=false; skipping traffic counts backfill")
        return 0

    traffic_counts_files = str(params.get("traffic_counts_files") or "").strip()
    traffic_stations_file = str(params.get("traffic_stations_file") or "").strip()

    if not traffic_counts_files:
        raise ValueError(
            "traffic_counts_files is required when run_traffic_counts_backfill=true. "
            "Use for example /opt/airflow/data/raw/traffic"
        )

    if traffic_stations_file:
        stations_path = Path(traffic_stations_file)
        if not stations_path.exists():
            raise FileNotFoundError(f"traffic_stations_file not found: {stations_path}")
    else:
        stations_path = None
        log.warning("traffic_stations_file is empty; station/location columns will be NULL")

    hook = _hook()
    run_id = _start_run(
        hook=hook,
        source_name="traffic_counts_backfill",
        message=f"Traffic counts CSV backfill from {traffic_counts_files}",
    )

    try:
        rows = load_traffic_counts_backfill(
            hook=hook,
            run_id=run_id,
            csv_paths=traffic_counts_files,
            stations_file=stations_path,
            schema=SCHEMA_NAME,
        )
        _finish_run(hook, run_id, "success", f"Backfill upserted {rows} traffic count rows")
        return rows
    except Exception as exc:
        _finish_run(hook, run_id, "failed", str(exc))
        raise


def ingest_traffic_hourly(**context) -> int:
    """
    Regulaarne liiklusandmete live/API laadimine.

    Käib iga DAG run'iga. Tark Tee ArcGIS kiht on live/snapshot tüüpi,
    seega seda kasutatakse edaspidiseks tunnipõhiseks kogumiseks.
    """
    hook = _hook()
    run_id = _start_run(
        hook=hook,
        source_name="traffic_hourly",
        message="Traffic hourly live/API load",
    )

    try:
        rows = load_traffic_live_recent(
            hook=hook,
            run_id=run_id,
            schema=SCHEMA_NAME,
        )
        _finish_run(hook, run_id, "success", f"Hourly load upserted {rows} traffic live rows")
        return rows
    except Exception as exc:
        _finish_run(hook, run_id, "failed", str(exc))
        raise


with DAG(
    dag_id="airwolf_pipeline",
    description="Laeb Airwolf projekti andmed staging skeemi ja käivitab dbt transformatsioonid",
    start_date=datetime(2025, 1, 1),
    schedule="@hourly",
    catchup=False,
    max_active_runs=1,
    params={
        # Backfill käivitub ainult käsitsi, kui run_weather_backfill=true.
        "run_weather_backfill": Param(False, type="boolean"),

         # Õhukvaliteedi backfill käivitub ainult käsitsi, kui run_air_quality_backfill=true.
        "run_air_quality_backfill": Param(False, type="boolean"),

        "year_start": Param(2026, type="integer", minimum=2000, maximum=2100),
        "month_start": Param(3, type="integer", minimum=1, maximum=12),
        "year_end": Param(2026, type="integer", minimum=2000, maximum=2100),
        "month_end": Param(5, type="integer", minimum=1, maximum=12),
        # Hourly laadimine.
        "weather_lookback_hours": Param(48, type="integer", minimum=1, maximum=168),
        "air_quality_lookback_hours": Param(48, type="integer", minimum=1, maximum=168),
        # Liiklusandmete CSV backfill käivitub ainult käsitsi, kui run_traffic_counts_backfill=true.
        "run_traffic_counts_backfill": Param(False, type="boolean"),
        "traffic_counts_files": Param("/opt/airflow/data/raw/traffic/counts", type="string"),
        "traffic_stations_file": Param("/opt/airflow/data/raw/traffic/stations/LL jaamad.xlsx", type="string"),
    },
    tags=["airwolf", "ingestion", "dbt"],
) as dag:

    create_tables_task = PythonOperator(
        task_id="create_tables",
        python_callable=create_tables,
    )

    ingest_weather_backfill_task = PythonOperator(
        task_id="ingest_weather_backfill",
        python_callable=ingest_weather_backfill,
    )

    ingest_weather_hourly_task = PythonOperator(
        task_id="ingest_weather_hourly",
        python_callable=ingest_weather_hourly,
    )


    ingest_air_quality_backfill_task = PythonOperator(
        task_id="ingest_air_quality_backfill",
        python_callable=ingest_air_quality_backfill,
    )

    ingest_air_quality_hourly_task = PythonOperator(
        task_id="ingest_air_quality_hourly",
        python_callable=ingest_air_quality_hourly,
    )

    ingest_traffic_counts_backfill_task = PythonOperator(
        task_id="ingest_traffic_counts_backfill",
        python_callable=ingest_traffic_counts_backfill,
    )

    ingest_traffic_hourly_task = PythonOperator(
        task_id="ingest_traffic_hourly",
        python_callable=ingest_traffic_hourly,
    )

    dbt_run = BashOperator(
        task_id="dbt_run",
        bash_command=(
            f"cd {DBT_PROJECT_DIR} && "
            # Käivitatakse enne mudeleid, et viitetabelid
            # (weather_stations, aq_stations) oleksid olemas enne vahe-mudeleid,
            # mis neid JOIN-iga kasutavad.
            "dbt seed --profiles-dir . && "
            "dbt run --profiles-dir ."
        ),
    )

    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=(
            f"cd {DBT_PROJECT_DIR} && "
            "dbt test --profiles-dir ."
        ),
    )

    create_tables_task >> [
        ingest_weather_backfill_task,
        ingest_weather_hourly_task,
        ingest_air_quality_backfill_task,
        ingest_air_quality_hourly_task,
        ingest_traffic_counts_backfill_task,
        ingest_traffic_hourly_task,
    ]

    [
        ingest_weather_backfill_task,
        ingest_weather_hourly_task,
        ingest_air_quality_backfill_task,
        ingest_air_quality_hourly_task,
        ingest_traffic_counts_backfill_task,
        ingest_traffic_hourly_task,
    ] >> dbt_run >> dbt_test

