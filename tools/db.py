"""
Lightweight Postgres helpers used by the API services and tools.

Single shared :class:`psycopg_pool.ConnectionPool`, lazily constructed.
DSN comes from the ``DATABASE_URL`` env var (loaded via :mod:`dotenv` for
CLI scripts).
"""
from __future__ import annotations

import os
import threading
from typing import Any, Iterable

from dotenv import load_dotenv
from psycopg_pool import ConnectionPool

load_dotenv()

_pool: ConnectionPool | None = None
_pool_lock = threading.Lock()


def _dsn() -> str:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError(
            "DATABASE_URL is not set — cannot open the Postgres connection pool",
        )
    return dsn


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = ConnectionPool(
                    _dsn(),
                    min_size=1,
                    max_size=8,
                    timeout=10,
                )
    return _pool


def _rows_as_dicts(cursor) -> list[dict[str, Any]]:
    cols = [c.name for c in cursor.description] if cursor.description else []
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def fetch_one(query: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
    pool = get_pool()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, list(params))
            row = cur.fetchone()
            if row is None:
                return None
            cols = [c.name for c in cur.description] if cur.description else []
            return dict(zip(cols, row))


def fetch_all(query: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
    pool = get_pool()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, list(params))
            return _rows_as_dicts(cur)


def execute(query: str, params: Iterable[Any] = ()) -> int:
    pool = get_pool()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, list(params))
            return cur.rowcount or 0


def execute_many(query: str, seq_of_params: Iterable[Iterable[Any]]) -> int:
    pool = get_pool()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(query, [list(p) for p in seq_of_params])
            return cur.rowcount or 0
