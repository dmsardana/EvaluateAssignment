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

ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")

# Add project root to path so tools.* and web.* imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("pipeline")

from web.api.services.credentials import REGISTRY, CredentialBroken  # noqa: E402


def _get_classroom():
    return REGISTRY.get("google_oauth").get_classroom()


def _get_drive():
    return REGISTRY.get("google_oauth").get_drive()


def tick():
    """Single pipeline iteration. Survives CredentialBroken by logging and returning."""
    load_dotenv(ENV_PATH)

    try:
        classroom = _get_classroom()
        drive = _get_drive()
    except CredentialBroken as exc:
        log.error(
            "CREDENTIAL_BROKEN %s %s — see /settings/credentials (%s)",
            exc.name,
            exc.status.value,
            exc.reason or "no detail",
        )
        return

    _run_iteration(classroom, drive)


def _run_iteration(classroom, drive):
    course_ids_str = os.getenv("CLASSROOM_COURSE_IDS", "").strip()
    reports_id = os.getenv("DRIVE_REPORTS_ID", "").strip()
    keys_id = os.getenv("DRIVE_KEYS_ID", "").strip()

    if not all([course_ids_str, reports_id, keys_id]):
        log.error("Missing env vars. Run tools/setup_drive.py first.")
        return

    course_ids = [c.strip() for c in course_ids_str.split(",") if c.strip()]

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

    # 1. Find pending submissions — but only act on them if AUTO_GRADE=1.
    # Default is UI-trigger-only: the web console's "Evaluate" buttons drive
    # grading. The pipeline still does AK generation + review-reply checking
    # above; this gate just skips the submission-grading block.
    auto_grade = os.getenv("AUTO_GRADE", "0").strip() == "1"
    if not auto_grade:
        log.info("Skipping submission grading — AUTO_GRADE not set "
                 "(set AUTO_GRADE=1 in .env for old behaviour).")
        return

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
            # Prefer teacher-set display_name over Classroom roster name.
            try:
                from tools.student_profiles import load_profiles as _lp
                _dn = (_lp(None, None).get(meta["student_id"], {}).get("display_name") or "").strip()
                if _dn:
                    meta["student_name"] = _dn
            except Exception:
                pass  # non-fatal

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
        tick()
        return

    load_dotenv(ENV_PATH)
    interval = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))
    log.info(f"Pipeline started. Polling every {interval}s. Ctrl+C to stop.")

    while True:
        try:
            tick()
        except KeyboardInterrupt:
            log.info("Stopped.")
            break
        except Exception as e:
            log.error(f"Unexpected error in pipeline loop: {e}", exc_info=True)

        log.info(f"Sleeping {interval}s…")
        time.sleep(interval)


if __name__ == "__main__":
    main()
