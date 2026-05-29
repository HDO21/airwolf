from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterable

import psycopg2
from psycopg2.extras import Json, execute_values


def _dsn() -> str:
    # Eelistus: üks POSTGRES_DSN. Kui seda pole, pannakse DSN kokku tavalistest env muutujatest.
    direct = os.getenv("POSTGRES_DSN")
    if direct:
        return direct
    return (
        f"host={os.getenv('POSTGRES_HOST', 'postgres')} "
        f"port={os.getenv('POSTGRES_PORT', '5432')} "
        f"dbname={os.getenv('POSTGRES_DB', 'postgres')} "
        f"user={os.getenv('POSTGRES_USER', 'postgres')} "
        f"password={os.getenv('POSTGRES_PASSWORD', 'postgres')}"
    )


@contextmanager
def get_conn():
    conn = psycopg2.connect(_dsn())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def insert_pipeline_run(conn, run_id: str, source_name: str, status: str, message: str | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO staging.pipeline_runs (run_id, source_name, status, message)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (run_id) DO UPDATE SET
                status = EXCLUDED.status,
                message = EXCLUDED.message,
                finished_at = CASE
                    WHEN EXCLUDED.status IN ('success', 'failed') THEN now()
                    ELSE staging.pipeline_runs.finished_at
                END
            """,
            (run_id, source_name, status, message),
        )


def upsert_rows(
    conn,
    table: str,
    rows: list[dict[str, Any]],
    columns: list[str],
    conflict_columns: list[str],
) -> int:
    """Insert/update dictionaries into a staging raw table.

    `columns` must match actual database column names. Every row also carries full source data
    in the `payload` JSONB column, so dbt can still access fields not explicitly typed here.
    """
    if not rows:
        return 0

    values = []
    for row in rows:
        values.append(tuple(Json(row.get(c)) if c == "payload" else row.get(c) for c in columns))

    col_sql = ", ".join(columns)
    conflict_sql = ", ".join(conflict_columns)
    update_sql = ", ".join(
        f"{c} = EXCLUDED.{c}" for c in columns if c not in conflict_columns
    )
    if update_sql:
        update_sql += ", _loaded_at = now()"
    else:
        update_sql = "_loaded_at = now()"

    query = f"""
        INSERT INTO {table} ({col_sql})
        VALUES %s
        ON CONFLICT ({conflict_sql}) DO UPDATE SET {update_sql}
    """
    with conn.cursor() as cur:
        execute_values(cur, query, values, page_size=1000)
    return len(rows)
