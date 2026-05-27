"""Read/write `report_view_settings` with an in-process cache.

On import, registers itself as the override loader for
`tools.report_view_config.view_for()`, so every report render checks the
Postgres-backed selection before falling back to DEFAULT_VIEWS.

The cache is invalidated on every write so a single API process always
sees its own writes. Multi-process deployments accept eventual
consistency on the order of seconds since the catalogue rarely changes.
"""
from __future__ import annotations

import json
import threading
from typing import Optional

from tools.db import execute, fetch_all
from tools.report_view_config import (
    defaults_for, register_override_loader,
)

_LOCK = threading.Lock()
_CACHE: dict[str, list[str]] | None = None


def invalidate_cache() -> None:
    global _CACHE
    with _LOCK:
        _CACHE = None


def _ensure_cache() -> dict[str, list[str]]:
    global _CACHE
    with _LOCK:
        if _CACHE is None:
            rows = fetch_all("SELECT tier, components FROM report_view_settings")
            _CACHE = {r["tier"]: list(r["components"]) for r in rows}
        return dict(_CACHE)


def load(tier: str) -> Optional[list[str]]:
    """Override loader contract: returns the persisted list for `tier`,
    or None when no row exists. Caller adds STRUCTURAL_LOCKED."""
    return _ensure_cache().get((tier or "").upper())


def load_all() -> dict[str, list[str]]:
    return _ensure_cache()


def save(tier: str, components: list[str]) -> None:
    payload = json.dumps(list(components))
    execute(
        """
        INSERT INTO report_view_settings (tier, components, updated_at)
        VALUES (%s, %s::jsonb, now())
        ON CONFLICT (tier) DO UPDATE
          SET components = EXCLUDED.components,
              updated_at = now()
        """,
        ((tier or "").upper(), payload),
    )
    invalidate_cache()


def reset(tier: str) -> list[str]:
    execute(
        "DELETE FROM report_view_settings WHERE tier = %s",
        ((tier or "").upper(),),
    )
    invalidate_cache()
    return defaults_for(tier)


def _safe_load(tier: str) -> Optional[list[str]]:
    try:
        return load(tier)
    except Exception:
        return None


register_override_loader(_safe_load)
