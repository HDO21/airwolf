from __future__ import annotations
import logging
import sys
import uuid

from pathlib import Path
from datetime import datetime

import pendulum

sys.path.append("/opt/airflow")

from datetime import datetime, timezone
from airflow import DAG
from airflow.sdk import Param
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook

from ingestion.ingest_weather import load_weather
#from ingestion.ingest_air_quality import load_air_quality
#from ingestion.ingest_traffic import load_traffic_live
log = logging.getLogger(__name__)

POSTGRES_CONN_ID = "analytics_db"
SCHEMA_NAME = "staging"
CREATE_TABLES_SQL = Path("/opt/airflow/sql/create_tables.sql")
DBT_PROJECT_DIR = "/opt/airflow/dbt_project"


def _hook() -> PostgresHook:
    """Tagastab ühenduse sinu analytics-db andmebaasi vastu.

    See kasutab docker-compose.yml failis defineeritud ühendust:
    AIRFLOW_CONN_ANALYTICS_DB=postgresql://...@analytics-db:5432/...
    """
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
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
) -> str:
    """Lisab staging.pipeline_runs tabelisse uue jooksu staatusega running."""
    run_id = str(uuid.uuid4())

    hook.run(
        """
        INSERT INTO staging.pipeline_runs
            (run_id, source_name, started_at, finished_at, status)
        VALUES
            (%s, %s,  %s, %s, 'running')
        """,
        parameters=(run_id, source_name, started_at, finished_at),
    )

    return run_id


def _finish_run(
    hook: PostgresHook,
    run_id: uuid.UUID,
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


def ingest_weather(**context) -> None:
    hook = _hook()
    year_start, month_start, year_end, month_end, period_start, period_end = _period_from_params(context)
    run_id = _start_run(hook, "weather", period_start, period_end)

    try:
        load_weather(
            hook=hook,
            run_id=run_id,
            year_start=year_start,
            month_start=month_start,
            year_end=year_end,
            month_end=month_end,
            schema=SCHEMA_NAME,
        )
        _finish_run(hook, run_id, "success")
    except Exception as exc:
        _finish_run(hook, run_id, "failed", str(exc))
        raise


def ingest_air_quality(**context) -> None:
    hook = _hook()
    year_start, month_start, year_end, month_end, period_start, period_end = _period_from_params(context)
    run_id = _start_run(hook, "air_quality", period_start, period_end)

    try:
        load_air_quality(
            hook=hook,
            run_id=run_id,
            year_start=year_start,
            month_start=month_start,
            year_end=year_end,
            month_end=month_end,
            schema=SCHEMA_NAME,
        )
        _finish_run(hook, run_id, "success")
    except Exception as exc:
        _finish_run(hook, run_id, "failed", str(exc))
        raise


def ingest_traffic_live(**context) -> None:
    hook = _hook()
    run_id = _start_run(hook, "traffic_live")

    try:
        load_traffic_live(
            hook=hook,
            run_id=run_id,
            schema=SCHEMA_NAME,
        )
        _finish_run(hook, run_id, "success")
    except Exception as exc:
        _finish_run(hook, run_id, "failed", str(exc))
        raise


def ingest_traffic_backfill(**context) -> None:
    """Laeb liikluse ajaloolise CSV ainult siis, kui DAG param traffic_backfill_file on antud."""
    params = context["params"]
    traffic_backfill_file = str(params.get("traffic_backfill_file") or "").strip()
    traffic_stations_file = str(params.get("traffic_stations_file") or "").strip()

    if not traffic_backfill_file:
        log.info("traffic_backfill_file is empty; skipping traffic backfill")
        return

    csv_path = Path(traffic_backfill_file)
    stations_path = Path(traffic_stations_file) if traffic_stations_file else None

    if not csv_path.exists():
        raise FileNotFoundError(f"traffic_backfill_file not found: {csv_path}")

    if stations_path is not None and not stations_path.exists():
        raise FileNotFoundError(f"traffic_stations_file not found: {stations_path}")

    hook = _hook()
    run_id = _start_run(hook, "traffic_backfill")

    try:
        load_traffic_backfill(
            hook=hook,
            run_id=run_id,
            csv_path=csv_path,
            stations_file=stations_path,
            schema=SCHEMA_NAME,
        )
        _finish_run(hook, run_id, "success")
    except Exception as exc:
        _finish_run(hook, run_id, "failed", str(exc))
        raise


with DAG(
    dag_id="airwolf_pipeline",
    description="Laeb Airwolf projekti andmed staging skeemi ja käivitab dbt transformatsioonid",
    start_date=datetime(2026, 1, 1),
    schedule="@daily",
    catchup=False,
    params={
        "year_start": Param(2025, type="integer", minimum=2000, maximum=2100),
        "month_start": Param(1, type="integer", minimum=1, maximum=12),
        "year_end": Param(2025, type="integer", minimum=2000, maximum=2100),
        "month_end": Param(12, type="integer", minimum=1, maximum=12),
        "traffic_backfill_file": Param("", type="string"),
        "traffic_stations_file": Param("", type="string"),
    },
    tags=["airwolf", "ingestion", "dbt"],
) as dag:

    create_tables_task = PythonOperator(
        task_id="create_tables",
        python_callable=create_tables,
    )

    ingest_weather_task = PythonOperator(
        task_id="ingest_weather",
        python_callable=ingest_weather,
    )

    # ingest_air_quality_task = PythonOperator(
    #     task_id="ingest_air_quality",
    #     python_callable=ingest_air_quality,
    # )

    # ingest_traffic_live_task = PythonOperator(
    #     task_id="ingest_traffic_live",
    #     python_callable=ingest_traffic_live,
    # )

    # ingest_traffic_backfill_task = PythonOperator(
    #     task_id="ingest_traffic_backfill",
    #     python_callable=ingest_traffic_backfill,
    # )

    # dbt_run = BashOperator(
    #     task_id="dbt_run",
    #     bash_command=(
    #         f"cd {DBT_PROJECT_DIR} && "
    #         "dbt seed --profiles-dir . && "
    #         "dbt run --profiles-dir ."
    #     ),
    # )

    # dbt_test = BashOperator(
    #     task_id="dbt_test",
    #     bash_command=(
    #         f"cd {DBT_PROJECT_DIR} && "
    #         "dbt test --profiles-dir ."
    #     ),
    # )

    create_tables_task >> [
        ingest_weather_task]
        #ingest_air_quality_task,
        #ingest_traffic_live_task,
        #ingest_traffic_backfill_task,
     #>> dbt_run >> dbt_test
