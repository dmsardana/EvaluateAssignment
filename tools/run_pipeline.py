"""
Main orchestrator. Polls Google Classroom for new submissions and runs the
full evaluation pipeline for each: download → evaluate → report → upload → track.

Usage:
    python tools/run_pipeline.py              # continuous polling loop
    python tools/run_pipeline.py --once       # process pending now and exit
"""

import json
import logging
import os
import sys
import time

from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")

# Add project root to path so tools.* imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("pipeline")


def get_creds():
    token_path = os.path.join(os.path.dirname(__file__), "..", "token.json")
    from tools.setup_drive import SCOPES
    creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


def run_once():
    load_dotenv(ENV_PATH)

    course_ids_str = os.getenv("CLASSROOM_COURSE_IDS", "").strip()
    reports_id = os.getenv("DRIVE_REPORTS_ID", "").strip()
    keys_id = os.getenv("DRIVE_KEYS_ID", "").strip()

    if not all([course_ids_str, reports_id, keys_id]):
        log.error("Missing env vars. Run tools/setup_drive.py first.")
        return

    course_ids = [c.strip() for c in course_ids_str.split(",") if c.strip()]
    creds = get_creds()
    classroom = build("classroom", "v1", credentials=creds)
    drive = build("drive", "v3", credentials=creds)

    # 0a. Generate answer keys for any new courseworks (auto-detect)
    log.info("Checking for assignments needing answer keys…")
    from tools.generate_answer_key import main as ak_main
    try:
        ak_main_args_backup = sys.argv
        sys.argv = ["generate_answer_key.py"]  # process all pending
        ak_main()
        sys.argv = ak_main_args_backup
    except SystemExit:
        sys.argv = ak_main_args_backup
    except Exception as e:
        log.error(f"  AK generation step failed: {e}")

    # 0b. Check for teacher review replies and trigger any regenerations
    log.info("Checking review replies…")
    try:
        from tools.check_review_replies import main as review_main
        review_main()
    except Exception as e:
        log.error(f"  Review-check step failed: {e}")

    # Load review state to gate evaluation behind approval
    from tools.review_state import load_state, is_approved
    review_state = load_state(drive, keys_id)

    # 1. Find pending submissions
    from tools.watch_classroom import list_pending
    from datetime import datetime, timezone
    cutoff = None
    cutoff_str = os.getenv("CUTOFF_DATE", "").strip()
    if cutoff_str:
        cutoff = datetime.fromisoformat(cutoff_str).replace(tzinfo=timezone.utc)
    log.info("Checking for new submissions…")
    pending = list_pending(course_ids, classroom, drive, reports_id, cutoff=cutoff)
    log.info(f"  {len(pending)} pending submission(s)")

    for sub in pending:
        label = f"{sub['assignment_type']} {sub['assignment_code']} / {sub['student_name']}"

        # Gate: only evaluate if the answer key has been APPROVED
        if not is_approved(review_state, sub["coursework_id"]):
            log.info(f"⏸  SKIP (key not approved): {label}")
            continue

        log.info(f"→ Processing: {label}")

        try:
            # 2. Download PDFs
            from tools.download_pdf import download_file, find_answer_key

            student_name_clean = sub["student_name"].replace(" ", "")
            submission_filename = (
                f"{sub['assignment_type']}_{sub['assignment_code']}_"
                f"{sub['student_id']}_{student_name_clean}.pdf"
            )
            tmp_dir = os.path.join(os.path.dirname(__file__), "..", ".tmp", "submissions")
            os.makedirs(tmp_dir, exist_ok=True)
            submission_path = os.path.join(tmp_dir, submission_filename)

            log.info(f"  Downloading submission…")
            download_file(drive, sub["drive_file_id"], submission_path)

            key_file_id = find_answer_key(
                drive, keys_id, sub["assignment_type"], sub["assignment_code"]
            )
            key_path = os.path.join(
                tmp_dir,
                f"{sub['assignment_type']}_{sub['assignment_code']}_KEY.pdf"
            )
            download_file(drive, key_file_id, key_path)
            log.info(f"  Downloaded answer key")

            meta = {
                "submission_path": submission_path,
                "answer_key_path": key_path,
                "student_name": sub["student_name"],
                "student_id": sub["student_id"],
                "assignment_type": sub["assignment_type"],
                "assignment_code": sub["assignment_code"],
            }

            # 3. Evaluate
            log.info(f"  Evaluating with Claude…")
            from tools.evaluate_pdf import evaluate
            evaluation = evaluate(submission_path, key_path, meta)
            pct = evaluation["summary"]["percentage"]
            log.info(f"  Score: {pct}%")

            # 4. Generate report
            log.info(f"  Generating LaTeX report…")
            from tools.generate_report import generate
            pdf_path = generate(evaluation)
            log.info(f"  Report: {pdf_path}")

            # 5. Upload report
            log.info(f"  Uploading report to Drive…")
            from tools.upload_report import upload
            upload(pdf_path, reports_id)

            # 6. Track scores
            from tools.track_scores import track
            track(evaluation, reports_id)

            qualifies = evaluation["summary"].get("qualifies_for")
            if qualifies:
                log.info(f"  ★ {sub['student_name']} qualifies for {qualifies}!")
            else:
                log.info(f"  ✓ Done — does not yet qualify for next level")

        except FileNotFoundError as e:
            log.error(f"  SKIPPED — {e}")
        except Exception as e:
            log.error(f"  FAILED — {label}: {e}", exc_info=True)


def main():
    run_once_mode = "--once" in sys.argv

    if run_once_mode:
        run_once()
        return

    load_dotenv(ENV_PATH)
    interval = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))
    log.info(f"Pipeline started. Polling every {interval}s. Ctrl+C to stop.")

    while True:
        try:
            run_once()
        except KeyboardInterrupt:
            log.info("Stopped.")
            break
        except Exception as e:
            log.error(f"Unexpected error in pipeline loop: {e}", exc_info=True)

        log.info(f"Sleeping {interval}s…")
        time.sleep(interval)


if __name__ == "__main__":
    main()
