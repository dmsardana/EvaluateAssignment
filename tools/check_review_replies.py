"""
Poll Gmail for replies to outstanding answer-key review emails.

For every coursework whose state is PENDING_REVIEW or NEEDS_REGEN:
  - Search inbox for replies in the original thread
  - Parse the latest reply text:
      * If "OK <OTP>" only → mark all questions approved → status = APPROVED
      * If "Q3, Q5-7 reprocess <OTP>" → mark those needs_rework, others approved → status = NEEDS_REGEN
      * Without matching OTP → ignore
  - For NEEDS_REGEN entries, automatically invoke generate_answer_key.py --regen

Usage:
    python tools/check_review_replies.py            # one-shot check
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from googleapiclient.discovery import build

ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")


# ── Reply parser ───────────────────────────────────────────────────────────────
QUOTE_HEADER_RE = re.compile(
    r"(?im)^\s*On\s.{1,200}\bwrote:\s*$|"
    r"^\s*-{2,}\s*Original Message\s*-{2,}\s*$|"
    r"^\s*From:\s.+$"
)


def strip_quoted_content(text: str) -> str:
    """
    Remove the quoted original message from a reply email body.
    Handles 'On <date>...wrote:' headers, '> '-prefixed lines, and
    '-- Original Message --' separators.
    """
    if not text:
        return ""
    # Cut at the first quote-header line we find
    m = QUOTE_HEADER_RE.search(text)
    if m:
        text = text[: m.start()]
    # Drop any remaining '> '-prefixed lines (in case the header didn't match)
    lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith(">")]
    # Drop signature delimiter "-- " line and everything after
    out = []
    for ln in lines:
        if ln.strip() == "--":
            break
        out.append(ln)
    return "\n".join(out).strip()


def parse_reply(text: str, otp: str, n_questions: int,
                from_address: str = "", expected_address: str = "") -> dict:
    """
    Parse a reply email body.

    Authentication: caller passes from_address (Gmail-verified). If it matches
    expected_address (TEACHER_EMAIL), the reply is trusted even without OTP.
    OTP is supplementary evidence.

    Returns:
        {"verdict": "approved" | "rework" | "invalid",
         "rework_qs": [3, 5, 6, 7]}
    """
    body = strip_quoted_content(text)
    upper = body.upper()

    # Authenticate
    sender_ok = (
        bool(expected_address)
        and bool(from_address)
        and expected_address.strip().lower() in from_address.strip().lower()
    )
    otp_ok = bool(otp) and otp.upper() in upper
    if not (sender_ok or otp_ok):
        return {"verdict": "invalid", "rework_qs": []}

    rework_keywords = re.compile(
        r"\b(REPROCESS|REDO|REWORK|RERUN|REGENERATE|WRONG|INCORRECT)\b",
        re.IGNORECASE,
    )

    if not rework_keywords.search(upper):
        # No rework keyword — treat as full approval
        return {"verdict": "approved", "rework_qs": []}

    # Extract specific Q numbers (ranges + singles)
    rework_qs: set[int] = set()
    for m in re.finditer(r"Q\s*(\d+)\s*[-–]\s*Q?\s*(\d+)", upper):
        a, b = int(m.group(1)), int(m.group(2))
        for n in range(min(a, b), max(a, b) + 1):
            rework_qs.add(n)
    for m in re.finditer(r"Q\s*(\d+)\b", upper):
        rework_qs.add(int(m.group(1)))

    # Generic "redo all" / "all wrong" → flag every question
    blanket_rework = re.search(
        r"\b(ALL|EVERYTHING|ENTIRE|FULL)\s+(WRONG|INCORRECT|REDO|RERUN|REWORK)\b"
        r"|\b(REDO|RERUN|REWORK|REGENERATE)\s+(ALL|EVERYTHING|ENTIRE)\b"
        r"|\bWRONG\s+SOLUTIONS\b",
        upper,
    )
    if blanket_rework or (rework_keywords.search(upper) and not rework_qs):
        # No specific Qs — treat as ALL questions need rework
        rework_qs = set(range(1, n_questions + 1))

    if not rework_qs:
        return {"verdict": "invalid", "rework_qs": []}

    return {"verdict": "rework", "rework_qs": sorted(rework_qs)}


# ── Main loop ──────────────────────────────────────────────────────────────────
def main():
    load_dotenv(ENV_PATH)

    from tools.email_helper import (
        get_creds,
        list_replies_by_thread,
        extract_plain_text,
    )
    from tools.review_state import load_state, save_state

    creds = get_creds()
    drive = build("drive", "v3", credentials=creds)

    keys_folder = os.getenv("DRIVE_KEYS_ID", "").strip()
    state = load_state(drive, keys_folder)

    pending = {
        cwid: e for cwid, e in state.items()
        if e.get("status") in ("PENDING_REVIEW", "NEEDS_REGEN")
    }

    if not pending:
        print("No keys awaiting review.", file=sys.stderr)
        return

    needs_regen = []

    for cwid, entry in pending.items():
        thread_id = entry.get("thread_id")
        otp = entry.get("current_otp", "")
        if not thread_id or not otp:
            continue

        print(f"Checking {entry['assignment_type']} {entry['assignment_code']}…", file=sys.stderr)

        try:
            messages = list_replies_by_thread(thread_id)
        except Exception as e:
            print(f"  thread fetch failed: {e}", file=sys.stderr)
            continue

        # The first message is our outgoing email; replies come after.
        replies = messages[1:] if len(messages) > 1 else []
        if not replies:
            print("  no replies yet", file=sys.stderr)
            continue

        # Use the latest reply
        latest = replies[-1]
        body = extract_plain_text(latest)
        from_addr = ""
        for h in latest.get("payload", {}).get("headers", []):
            if h.get("name", "").lower() == "from":
                from_addr = h.get("value", "")
                break

        n_q = len(entry.get("questions", []))
        teacher_email = os.getenv("TEACHER_EMAIL", "").strip()
        result = parse_reply(body, otp, n_q,
                             from_address=from_addr,
                             expected_address=teacher_email)

        if result["verdict"] == "invalid":
            print(f"  reply present but invalid (sender mismatch + OTP missing / unparseable)", file=sys.stderr)
            continue

        if result["verdict"] == "approved":
            entry["status"] = "APPROVED"
            entry["questions_status"] = ["approved"] * len(entry.get("questions", []))
            from datetime import datetime, timezone
            entry["approved_at"] = datetime.now(timezone.utc).isoformat()
            print(f"  ✓ APPROVED", file=sys.stderr)
        else:
            # rework
            qs_status = entry.get("questions_status", ["approved"] * len(entry.get("questions", [])))
            for n in result["rework_qs"]:
                if 0 <= n - 1 < len(qs_status):
                    qs_status[n - 1] = "needs_rework"
            for i, s in enumerate(qs_status):
                if s == "pending":
                    qs_status[i] = "approved"  # un-flagged Qs become approved
            entry["questions_status"] = qs_status
            entry["status"] = "NEEDS_REGEN"
            needs_regen.append(cwid)
            print(f"  ↻ NEEDS_REGEN for Q{result['rework_qs']}", file=sys.stderr)

    save_state(drive, keys_folder, state)

    # Auto-trigger regeneration for NEEDS_REGEN entries
    if needs_regen:
        print(f"\nRegenerating {len(needs_regen)} key(s)…", file=sys.stderr)
        from tools.generate_answer_key import (
            process_coursework,
            get_creds as gc,
        )
        creds2 = gc()
        drive2 = build("drive", "v3", credentials=creds2)
        classroom2 = build("classroom", "v1", credentials=creds2)
        for cwid in needs_regen:
            entry = state[cwid]
            redo = [i + 1 for i, s in enumerate(entry["questions_status"]) if s == "needs_rework"]
            print(f"  → {entry['assignment_type']} {entry['assignment_code']} Q{redo}", file=sys.stderr)
            new_entry = process_coursework(
                entry["course_id"], entry["coursework_id"],
                entry["assignment_type"], entry["assignment_code"], entry["assignment_title"],
                drive2, classroom2, keys_folder, state, redo_q_nums=redo,
            )
            state[cwid] = new_entry
            save_state(drive2, keys_folder, state)


if __name__ == "__main__":
    main()
