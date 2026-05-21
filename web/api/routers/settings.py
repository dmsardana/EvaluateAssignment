"""Rubric + thresholds + tier-cutoff endpoints.

The rubric dimension list is static (locked by the grading pipeline);
the bands and tier cutoffs are runtime-tunable and persisted to the
project root `.env` file via :func:`dotenv.set_key`.
"""
from __future__ import annotations

import os
from pathlib import Path

import dotenv
from fastapi import APIRouter, HTTPException

from tools import tier_config
from web.api.models import (
    RubricDimension,
    RubricResponse,
    Thresholds,
    TierCutoffs,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])

# parents[3] from web/api/routers/settings.py resolves to the repo root.
ENV_PATH = str(Path(__file__).resolve().parents[3] / ".env")

# Locked dimensions — match the grading prompt in tools/evaluate_pdf.py.
_DIMENSIONS: list[RubricDimension] = [
    RubricDimension(
        key="cu",
        name="Concept Understanding",
        weight=0.40,
        description=(
            "Does the student grasp the underlying mathematical idea? "
            "Identifies what's being asked and which tools apply."
        ),
    ),
    RubricDimension(
        key="am",
        name="Approach & Method",
        weight=0.20,
        description=(
            "Is the chosen approach efficient and rigorous? Sets up the "
            "problem cleanly before computing."
        ),
    ),
    RubricDimension(
        key="ss",
        name="Step-by-step",
        weight=0.20,
        description=(
            "Are the algebraic and arithmetic steps shown completely, in "
            "order, with no leaps?"
        ),
    ),
    RubricDimension(
        key="na",
        name="Numerical Accuracy",
        weight=0.10,
        description=(
            "Are the final values correct? No sign errors, no "
            "transposition, no off-by-one."
        ),
    ),
    RubricDimension(
        key="pr",
        name="Presentation",
        weight=0.10,
        description=(
            "Is the work legible, organised, with units and final-answer "
            "boxes where expected?"
        ),
    ),
]

_BAND_LABELS = {
    "trailblazer": "Trailblazer",
    "qualifier": "Qualifier",
    "developing": "Developing",
    "foundational_gaps": "Foundational Gaps",
}

# Default band cutoffs match what the live pipeline has been using.
_DEFAULT_THRESHOLDS = {"trailblazer": 75, "qualifier": 60, "developing": 40}


def _read_threshold(name: str, fallback: int) -> int:
    raw = (os.environ.get(f"THRESHOLD_{name.upper()}") or "").strip()
    if not raw:
        return fallback
    try:
        return max(0, min(100, int(raw)))
    except ValueError:
        return fallback


def _current_thresholds() -> Thresholds:
    return Thresholds(
        trailblazer=_read_threshold("trailblazer", _DEFAULT_THRESHOLDS["trailblazer"]),
        qualifier=_read_threshold("qualifier", _DEFAULT_THRESHOLDS["qualifier"]),
        developing=_read_threshold("developing", _DEFAULT_THRESHOLDS["developing"]),
    )


@router.get("/rubric", response_model=RubricResponse)
def get_rubric() -> RubricResponse:
    return RubricResponse(
        dimensions=_DIMENSIONS,
        per_question_scores=[0.0, 0.5, 1.0],
        bands=_current_thresholds(),
        band_labels=_BAND_LABELS,
    )


@router.get("/thresholds", response_model=Thresholds)
def get_thresholds() -> Thresholds:
    return _current_thresholds()


@router.put("/thresholds", response_model=Thresholds)
def put_thresholds(body: Thresholds) -> Thresholds:
    pairs = {
        "THRESHOLD_TRAILBLAZER": str(body.trailblazer),
        "THRESHOLD_QUALIFIER": str(body.qualifier),
        "THRESHOLD_DEVELOPING": str(body.developing),
    }
    try:
        for k, v in pairs.items():
            dotenv.set_key(ENV_PATH, k, v)
            os.environ[k] = v
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"failed to persist: {exc}")
    return _current_thresholds()


@router.get("/tier-cutoffs", response_model=TierCutoffs)
def get_tier_cutoffs() -> TierCutoffs:
    return TierCutoffs(
        WA=tier_config.get_pass_pct("WA"),
        QA=tier_config.get_pass_pct("QA"),
        AA=tier_config.get_pass_pct("AA"),
        ZA=tier_config.get_pass_pct("ZA"),
    )


@router.put("/tier-cutoffs", response_model=TierCutoffs)
def put_tier_cutoffs(body: TierCutoffs) -> TierCutoffs:
    """Update WA/QA/ZA cutoffs. AA is terminal; sending a value for AA is
    accepted but ignored (the tier config keeps it None)."""
    updates: dict[str, int | None] = {
        "TIER_PASS_PCT_WA": body.WA,
        "TIER_PASS_PCT_QA": body.QA,
        # AA is terminal — never persist a value for it.
        "TIER_PASS_PCT_ZA": body.ZA,
    }
    try:
        for k, v in updates.items():
            if v is None:
                dotenv.set_key(ENV_PATH, k, "")
                os.environ.pop(k, None)
            else:
                dotenv.set_key(ENV_PATH, k, str(v))
                os.environ[k] = str(v)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"failed to persist: {exc}")
    return get_tier_cutoffs()
