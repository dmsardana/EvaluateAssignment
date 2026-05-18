"""Postgres I/O for credentials_health. The only thing that knows the table schema."""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row

from web.api.services.credentials import Status


def _conn() -> psycopg.Connection:
    return psycopg.connect(os.environ["DATABASE_URL"])


_UPSERT_SQL = """
INSERT INTO credentials_health
    (name, status, last_checked_at, last_ok_at, last_error, updated_at)
VALUES
    (%(name)s, %(status)s, %(now)s,
     CASE WHEN %(status)s = 'OK' THEN %(now)s ELSE NULL END,
     %(last_error)s, %(now)s)
ON CONFLICT (name) DO UPDATE SET
    status            = EXCLUDED.status,
    last_checked_at   = EXCLUDED.last_checked_at,
    last_ok_at        = CASE WHEN EXCLUDED.status = 'OK'
                              THEN EXCLUDED.last_checked_at
                              ELSE credentials_health.last_ok_at END,
    last_error        = EXCLUDED.last_error,
    updated_at        = EXCLUDED.updated_at;
"""


def upsert_health(name: str, status: Status, last_error: str | None, now: datetime) -> None:
    with _conn() as c, c.cursor() as cur:
        cur.execute(_UPSERT_SQL, {
            "name": name,
            "status": status.value,
            "now": now,
            "last_error": last_error,
        })


def read_all() -> list[dict[str, Any]]:
    with _conn() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT * FROM credentials_health ORDER BY name")
        return list(cur.fetchall())


def read_one(name: str) -> dict[str, Any] | None:
    with _conn() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT * FROM credentials_health WHERE name = %s", (name,))
        return cur.fetchone()


def update_notified_at(name: str, when: datetime) -> None:
    with _conn() as c, c.cursor() as cur:
        cur.execute(
            "UPDATE credentials_health SET notified_at = %s WHERE name = %s",
            (when, name),
        )


def update_recovery_started_at(name: str, when: datetime | None) -> None:
    with _conn() as c, c.cursor() as cur:
        cur.execute(
            "UPDATE credentials_health SET recovery_started_at = %s WHERE name = %s",
            (when, name),
        )


def delete_health(name: str) -> None:
    """Test-only helper. Not exposed via the API."""
    with _conn() as c, c.cursor() as cur:
        cur.execute("DELETE FROM credentials_health WHERE name = %s", (name,))
