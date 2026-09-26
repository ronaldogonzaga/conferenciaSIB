from contextlib import contextmanager
from typing import Any

import psycopg2
import psycopg2.extras

from config import Config


def get_connection():
    conn = psycopg2.connect(
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        dbname=Config.DB_NAME,
    )
    with conn.cursor() as cur:

        cur.execute(f'SET search_path TO "{Config.DB_SCHEMA}"')

        cur.execute("SET statement_timeout TO '90s'")
    conn.commit()
    return conn


@contextmanager
def db_cursor(dict_cursor: bool = True):
    conn = get_connection()
    try:
        factory = psycopg2.extras.RealDictCursor if dict_cursor else None
        cur = conn.cursor(cursor_factory=factory)
        try:
            yield cur
            conn.commit()
        finally:
            cur.close()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def fetch_all(sql: str, params: tuple | dict | None = None) -> list[dict[str, Any]]:
    with db_cursor(True) as cur:
        cur.execute(sql, params)
        return list(cur.fetchall())


def fetch_one(sql: str, params: tuple | dict | None = None) -> dict[str, Any] | None:
    with db_cursor(True) as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def fetch_count(sql: str, params: tuple | dict | None = None) -> int:
    with db_cursor(True) as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        if not row:
            return 0
        return int(next(iter(row.values())))


def execute_returning(sql: str, params: tuple | dict | None = None) -> list[dict[str, Any]]:
    with db_cursor(True) as cur:
        cur.execute(sql, params)
        try:
            return list(cur.fetchall())
        except psycopg2.ProgrammingError:
            return []


def test_connection() -> dict[str, Any]:
    row = fetch_one("SELECT current_database() AS db, current_user AS usr, current_schema() AS schema")
    return row or {}
