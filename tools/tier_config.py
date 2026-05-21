"""
Tier configuration — labels + default pass percentages per assignment type.

Tiers (per the project's WA → QA → AA promotion ladder, with ZA as a
diagnostic tier that promotes to a "pass terminal"):

    WA → QA (Warm-up → Qualifier)
    QA → AA (Qualifier → Achiever / Annual)
    AA      (terminal)
    ZA → AA (Diagnostic / Quiz → Achiever)

Pass percentages can be overridden per-tier via env vars:

    TIER_PASS_PCT_WA, TIER_PASS_PCT_QA, TIER_PASS_PCT_AA, TIER_PASS_PCT_ZA

Returning ``None`` from :func:`get_pass_pct` means the tier is terminal
(no promotion concept). Only AA is terminal in the default config.
"""
from __future__ import annotations

import os

TIER_CONFIG: dict[str, object] = {
    "WA": {"label": "Warm-up", "promotes_to": "QA", "default_pass_pct": 60},
    "QA": {"label": "Qualifier", "promotes_to": "AA", "default_pass_pct": 75},
    "AA": {"label": "Achiever", "promotes_to": None, "default_pass_pct": None},
    "ZA": {"label": "Quiz", "promotes_to": "AA", "default_pass_pct": 75},
}

_PASS_PCT_ENV_PREFIX = "TIER_PASS_PCT_"


def get_pass_pct(tier: str) -> int | None:
    """Return the integer pass percentage for ``tier`` or ``None`` if terminal.

    Env override wins when set and parseable. Otherwise falls back to
    ``TIER_CONFIG[tier]['default_pass_pct']``. Unknown tiers return ``None``.
    """
    cfg = TIER_CONFIG.get(tier)
    if not isinstance(cfg, dict):
        return None

    env_key = f"{_PASS_PCT_ENV_PREFIX}{tier}"
    raw = os.environ.get(env_key, "").strip()
    if raw:
        try:
            return max(0, min(100, int(raw)))
        except ValueError:
            pass

    default = cfg.get("default_pass_pct")
    if default is None:
        return None
    return max(0, min(100, int(default)))
