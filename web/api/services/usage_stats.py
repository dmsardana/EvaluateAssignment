"""Read the per-call usage_log JSONL files and surface the most-recent
evaluation row per (coursework_id, student_id).

Used by the queue-detail endpoint to attach time/tokens/cost to each
submission card. Cheap: tails the last N days of JSONL (small files,
hundreds of lines max per day) on every call. If this ever gets hot
enough to matter, swap for a Postgres usage_log table.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, timedelta

log = logging.getLogger(__name__)

# How many days of JSONL to scan when assembling per-submission stats.
# Evaluations >2 weeks old aren't useful at the queue-detail card level.
_LOOKBACK_DAYS = 14


def _log_dir() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    # web/api/services/ -> repo root -> .tmp/_usage
    repo_root = os.path.abspath(os.path.join(here, "..", "..", ".."))
    return os.path.join(repo_root, ".tmp", "_usage")


def _iter_recent_files() -> list[str]:
    """Return JSONL paths for the last _LOOKBACK_DAYS, newest first.
    Returns only files that actually exist."""
    out: list[str] = []
    today = date.today()
    for delta in range(_LOOKBACK_DAYS):
        d = today - timedelta(days=delta)
        path = os.path.join(_log_dir(), f"{d.isoformat()}.jsonl")
        if os.path.exists(path):
            out.append(path)
    return out


def latest_eval_by_student(coursework_id: str) -> dict[str, dict]:
    """Map student_id -> most-recent evaluation record dict for this
    coursework. Empty dict if no records found. Never raises."""
    if not coursework_id:
        return {}
    by_student: dict[str, dict] = {}
    for path in _iter_recent_files():
        try:
            with open(path, "r", encoding="utf-8") as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    if rec.get("purpose") != "evaluation":
                        continue
                    if rec.get("coursework_id") != coursework_id:
                        continue
                    sid = rec.get("student_id")
                    if not sid:
                        continue
                    prev = by_student.get(sid)
                    if prev is None or (rec.get("ts") or "") > (prev.get("ts") or ""):
                        by_student[sid] = rec
        except Exception as exc:  # noqa: BLE001
            log.warning("usage_log read failed for %s: %s", path, exc)
    return by_student


def summarize_for_submission(rec: dict | None) -> dict | None:
    """Trim a raw JSONL record down to the fields the queue UI shows.
    Returns None when there's no record (so the UI can render '—')."""
    if not rec:
        return None
    return {
        "ts": rec.get("ts"),
        "model": rec.get("model"),
        "input_tokens": int(rec.get("input_tokens") or 0),
        "output_tokens": int(rec.get("output_tokens") or 0),
        "cost_usd_est": float(rec.get("cost_usd_est") or 0.0),
        "duration_seconds": (
            float(rec["duration_seconds"])
            if rec.get("duration_seconds") is not None
            else None
        ),
    }
