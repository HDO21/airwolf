from __future__ import annotations

import os
from contextlib import contextmanager

import psycopg2


def _dsn() -> str:
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
    """Tagastab otse psycopg2 ühendusekeskkonna muutujate põhjal.

    Mõeldud lokaalse arenduse ja testimise jaoks, kus Airflow PostgresHook
    pole saadaval. Airflow DAG-i sees kasuta selle asemel
    PostgresHook(postgres_conn_id=…) — see loeb sama analytics-db ühenduse
    Airflow ühenduste salvestusest.
    """
    conn = psycopg2.connect(_dsn())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
