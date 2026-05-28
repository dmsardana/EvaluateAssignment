"""Single source of truth for LLM token/cost bookkeeping.

Every LLM call site in this project (AK generation, evaluation, self-heal
retries, future providers) MUST route through log_llm_call so daily and
per-student cost roll-ups stay accurate. Adding a new provider/model only
requires extending PRICES_PER_M and passing provider + model.

Persistence: one JSONL line per call at .tmp/_usage/YYYY-MM-DD.jsonl.
Per-student detail is also attached to the evaluation JSON by the caller.

Cost is an estimate using published vendor rates; reconcile against the
provider's billing dashboard for final numbers.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

PRICES_PER_M: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-6":  (3.00, 15.00),
    "claude-sonnet-4-5":  (3.00, 15.00),
    "claude-opus-4-7":    (15.00, 75.00),
    "claude-opus-4-6":    (15.00, 75.00),
    "claude-haiku-4-5":   (0.80, 4.00),
    "gemini-2.5-pro":     (1.25, 10.00),
    "gemini-2.5-flash":   (0.30, 2.50),
    "gpt-4o":             (2.50, 10.00),
    "gpt-4o-mini":        (0.15, 0.60),
    "gpt-5":              (5.00, 15.00),
}

_DEFAULT_RATE = (3.00, 15.00)


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    rate = PRICES_PER_M.get((model or "").lower(), _DEFAULT_RATE)
    in_tok = int(input_tokens or 0)
    out_tok = int(output_tokens or 0)
    return round((in_tok * rate[0] + out_tok * rate[1]) / 1_000_000, 4)


def _log_dir() -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        ".tmp", "_usage",
    )


def log_llm_call(
    *,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    purpose: str,
    **context: Any,
) -> dict:
    """Persist a single LLM call's usage + return the record dict.

    purpose: stable label, e.g. 'ak_generation', 'ak_self_heal',
             'evaluation', 'eval_self_heal'. Used for filtering rollups.
    context: arbitrary kwargs persisted alongside (student_id, assignment_code,
             coursework_id, submission_bytes, etc.).
    """
    rec = {
        "ts":             datetime.now(timezone.utc).isoformat(),
        "provider":       provider,
        "model":          model,
        "purpose":        purpose,
        "input_tokens":   int(input_tokens or 0),
        "output_tokens":  int(output_tokens or 0),
        "cost_usd_est":   estimate_cost(model, input_tokens, output_tokens),
        **context,
    }
    try:
        os.makedirs(_log_dir(), exist_ok=True)
        path = os.path.join(_log_dir(), f"{datetime.utcnow().strftime('%Y-%m-%d')}.jsonl")
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as exc:
        print(f"[usage] write failed: {exc}", file=sys.stderr)
    return rec
