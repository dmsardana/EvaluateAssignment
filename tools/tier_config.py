"""
Tier configuration — labels + default pass percentages per assignment type.

Tiers (per the project's WA → QA → AA promotion ladder, with ZA as a
diagnostic tier that promotes to a "pass terminal", and GA as an
in-class guided assignment that does not gate anything):

    WA → QA (Warm-up → Qualifier)
    QA → AA (Qualifier → Achiever / Annual)
    AA      (terminal)
    ZA → AA (Diagnostic / Quiz → Achiever)
    GA      (Guided Assignment — terminal, informational only)

Pass percentages can be overridden per-tier via env vars:

    TIER_PASS_PCT_WA, TIER_PASS_PCT_QA, TIER_PASS_PCT_AA,
    TIER_PASS_PCT_ZA, TIER_PASS_PCT_GA

Returning ``None`` from :func:`get_pass_pct` means the tier is terminal
(no promotion concept). AA is terminal; GA is terminal but still
reports a 60% informational pass threshold.
"""
from __future__ import annotations

import os

TIER_CONFIG: dict[str, object] = {
    "WA": {"label": "Warm-up",   "promotes_to": "QA",  "default_pass_pct": 60},
    "QA": {"label": "Qualifier", "promotes_to": "AA",  "default_pass_pct": 75},
    "AA": {"label": "Achiever",  "promotes_to": None,  "default_pass_pct": None},
    "ZA": {"label": "Quiz",      "promotes_to": "AA",  "default_pass_pct": 75},
    "GA": {"label": "Guided",    "promotes_to": None,  "default_pass_pct": 60},
}

# Single source of truth for "what tiers does the system accept?".
# Every other module that validates or enumerates tiers MUST import
# KNOWN_TIERS rather than hardcoding a tuple — that way adding a new
# tier means editing only TIER_CONFIG above. Locations that consume
# KNOWN_TIERS: tools/watch_classroom.py (parser whitelist),
# web/api/services/queue.py (courseWork filter), the frontend
# AssignmentType union (kept in sync manually).
KNOWN_TIERS: tuple[str, ...] = tuple(TIER_CONFIG.keys())

_PASS_PCT_ENV_PREFIX = "TIER_PASS_PCT_"


def tier_label(tier: str) -> str:
    """Short human label for a tier (e.g. "Warm-up"). Falls back to the
    tier code if the tier is unknown — never raises."""
    cfg = TIER_CONFIG.get(tier)
    if isinstance(cfg, dict):
        lbl = cfg.get("label")
        if isinstance(lbl, str) and lbl:
            return lbl
    return tier


def promotes_to(tier: str) -> str | None:
    """Tier that this one promotes into, or None if terminal/unknown."""
    cfg = TIER_CONFIG.get(tier)
    if isinstance(cfg, dict):
        nxt = cfg.get("promotes_to")
        if isinstance(nxt, str):
            return nxt
    return None


def is_terminal(tier: str) -> bool:
    """True if reaching this tier does not promote anywhere else."""
    return promotes_to(tier) is None


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
