"""
Poll Google Classroom for TURNED_IN submissions that haven't been evaluated yet.
Cross-references scores.csv on Drive to skip already-processed submissions.

Returns a list of dicts, one per pending submission, printed as JSON.

Usage:
    python tools/watch_classroom.py
"""

import json
import logging
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")
SCORES_FILENAME = "scores.csv"

log = logging.getLogger(__name__)

# Order matters — longer keywords first to win against shorter substring matches.
TYPE_MAP = [
    ("WARM-UP", "WA"), ("WARM UP", "WA"), ("WARM", "WA"),
    ("QUALIFIER", "QA"), ("QUALIFYING", "QA"),
    ("ACHIEVERS", "AA"), ("ACHIEVER", "AA"),
    ("QUIZ", "ZA"),
    ("WA", "WA"), ("QA", "QA"), ("AA", "AA"), ("ZA", "ZA"),
]

# Match the parenthetical "(Code: TYPE IDENTIFIER ...)"
CODE_RE = re.compile(r"\(\s*Code\s*:\s*(.+?)\s*\)", re.IGNORECASE)

# Match free-form "Code XXX" — the identifier is captured up to a delimiter (| or end)
INLINE_CODE_RE = re.compile(
    r"\bCode\s*[:\-]?\s*([A-Za-z][\w\-]*)",
    re.IGNORECASE,
)
# Match free-form "Type WA" / "Type: QA" / "[QA]" etc.
INLINE_TYPE_RE = re.compile(
    r"\bType\s*[:\-]?\s*(WA|QA|AA|ZA)\b|\[(WA|QA|AA|ZA)\]",
    re.IGNORECASE,
)


def parse_assignment_meta(title: str) -> tuple[str, str]:
    """
    Extract (TYPE, CODE) from a Classroom assignment title.

    Supported formats (priority order):
      1. '... (Code: TYPE IDENTIFIER)'        → type=TYPE,  code=IDENTIFIER
         e.g. '02b A01 Continuity (Code: QA DA-MT-2025 CG-LCD-01)'
              → type='QA', code='DA-MT-2025_CG-LCD-01'
      2. '... | Code DOM2 | Type WA'          → type=WA,    code=DOM2
      3. '04 Logarithms [QA]'                 → type=QA,    code='04' (number fallback)

    Returns ('UNKNOWN', '00') if nothing recognisable.
    """
    # Format 1: parenthetical
    m = CODE_RE.search(title)
    if m:
        inner = m.group(1).strip()
        tokens = inner.split()
        if tokens:
            first_upper = tokens[0].upper()
            if first_upper in {"WA", "QA", "AA", "ZA"}:
                code = "_".join(tokens[1:]).upper() if len(tokens) > 1 else "UNCODED"
                return first_upper, code
            code = "_".join(tokens).upper()
            return _detect_type_from_text(title), code

    # Format 2: inline "Code XXX" + "Type YY" or "[YY]"
    code_m = INLINE_CODE_RE.search(title)
    type_m = INLINE_TYPE_RE.search(title)
    if code_m and type_m:
        code = code_m.group(1).upper()
        atype = (type_m.group(1) or type_m.group(2)).upper()
        return atype, code

    # Format 3: number + bracketed type
    return _detect_type_from_text(title), _extract_number_fallback(title)


def _detect_type_from_text(text: str) -> str:
    upper = text.upper()
    for keyword, code in TYPE_MAP:
        if re.search(rf"\b{re.escape(keyword)}\b", upper):
            return code
    return "UNKNOWN"


def _extract_number_fallback(title: str) -> str:
    m = re.search(r"\b(\d{1,2})\b", title)
    return m.group(1).zfill(2) if m else "00"


def parse_iso_datetime(s: str) -> datetime:
    """Parse Classroom's RFC 3339 timestamps (e.g. '2026-05-08T14:23:11.123Z')."""
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def load_processed_keys(drive, reports_folder_id: str) -> set:
    """Return set of '{code}_{student_id}' strings already in scores.csv.

    Intentionally excludes assignment_type from the key so that a Classroom
    title rename (e.g. QA→WA) does not cause the same submission to be
    re-evaluated and double-counted in scores.csv.
    """
    query = (
        f"name='{SCORES_FILENAME}' and '{reports_folder_id}' in parents and trashed=false"
    )
    results = drive.files().list(q=query, fields="files(id)").execute()
    files = results.get("files", [])
    if not files:
        return set()

    import io
    from googleapiclient.http import MediaIoBaseDownload
    file_id = files[0]["id"]
    request = drive.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()

    processed = set()
    for line in buf.getvalue().decode("utf-8").splitlines()[1:]:  # skip header
        parts = line.split(",")
        if len(parts) >= 3:
            # parts[0]=assignment_type, parts[1]=assignment_code, parts[2]=student_id
            processed.add(f"{parts[1]}_{parts[2]}")  # code_studentId (type-agnostic)
    return processed


def list_pending(
    course_ids: list,
    classroom,
    drive,
    reports_folder_id: str,
    cutoff: datetime | None = None,
) -> list:
    processed = load_processed_keys(drive, reports_folder_id)
    pending = []

    for course_id in course_ids:
        # Get student roster for name lookup
        roster = {}
        try:
            students_resp = classroom.courses().students().list(courseId=course_id).execute()
            for s in students_resp.get("students", []):
                profile = s.get("profile", {})
                roster[s["userId"]] = profile.get("name", {}).get("fullName", s["userId"])
        except Exception:
            pass

        # Get all coursework — skip courses where account lacks teacher-level access
        try:
            cw_resp = classroom.courses().courseWork().list(courseId=course_id).execute()
        except Exception as e:
            print(f"  Skipping course {course_id}: {e}", file=sys.stderr)
            continue
        for cw in cw_resp.get("courseWork", []):
            title = cw.get("title", "")
            asgn_type, asgn_code = parse_assignment_meta(title)

            if asgn_type in ("ZA", "UNKNOWN"):
                continue  # ZA handled by Google Forms; UNKNOWN skipped

            # Get all TURNED_IN submissions for this coursework
            try:
                subs_resp = (
                    classroom.courses()
                    .courseWork()
                    .studentSubmissions()
                    .list(courseId=course_id, courseWorkId=cw["id"], states=["TURNED_IN"])
                    .execute()
                )
            except Exception as e:
                print(f"  Skipping {course_id}/{cw['id']}: {e}", file=sys.stderr)
                continue

            for sub in subs_resp.get("studentSubmissions", []):
                # Date filter
                if cutoff:
                    sub_time = sub.get("updateTime") or sub.get("creationTime")
                    if sub_time:
                        try:
                            if parse_iso_datetime(sub_time) < cutoff:
                                continue
                        except ValueError:
                            pass

                student_id = sub["userId"]
                key = f"{asgn_code}_{student_id}"  # type-agnostic; matches load_processed_keys
                if key in processed:
                    continue

                attachments = (
                    sub.get("assignmentSubmission", {}).get("attachments", [])
                )
                drive_files = [
                    a["driveFile"]
                    for a in attachments
                    if "driveFile" in a
                ]
                if not drive_files:
                    continue  # no PDF attached

                pending.append({
                    "course_id": course_id,
                    "coursework_id": cw["id"],
                    "submission_id": sub["id"],
                    "student_id": student_id,
                    "student_name": roster.get(student_id, student_id),
                    "assignment_type": asgn_type,
                    "assignment_code": asgn_code,
                    "assignment_title": title,
                    "submitted_at": sub.get("updateTime", ""),
                    "drive_file_id": drive_files[0]["id"],
                    "drive_file_name": drive_files[0].get("title", "submission.pdf"),
                })

    return pending


def main():
    load_dotenv(ENV_PATH)

    course_ids_str = os.getenv("CLASSROOM_COURSE_IDS", "").strip()
    if not course_ids_str:
        print("CLASSROOM_COURSE_IDS not set. Run tools/setup_drive.py first.", file=sys.stderr)
        sys.exit(1)

    reports_id = os.getenv("DRIVE_REPORTS_ID", "").strip()
    course_ids = [c.strip() for c in course_ids_str.split(",") if c.strip()]

    cutoff = None
    cutoff_str = os.getenv("CUTOFF_DATE", "").strip()
    if cutoff_str:
        cutoff = datetime.fromisoformat(cutoff_str).replace(tzinfo=timezone.utc)
        print(f"Filtering to submissions on/after {cutoff.isoformat()}", file=sys.stderr)

    from web.api.services.credentials import REGISTRY, CredentialBroken
    try:
        classroom = REGISTRY.get("google_oauth").get_classroom()
        drive = REGISTRY.get("google_oauth").get_drive()
    except CredentialBroken as exc:
        log.error(
            "CREDENTIAL_BROKEN %s %s — see /settings/credentials (%s)",
            exc.name,
            exc.status.value,
            exc.reason or "no detail",
        )
        sys.exit(1)

    pending = list_pending(course_ids, classroom, drive, reports_id, cutoff=cutoff)
    print(json.dumps(pending, indent=2))
    print(f"\n{len(pending)} pending submission(s).", file=sys.stderr)


if __name__ == "__main__":
    main()
