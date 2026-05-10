"""
Download a student's submission PDF and the matching answer key from Drive.

Usage:
    python tools/download_pdf.py '<submission_json>'

where submission_json is a single item from watch_classroom.py output.

Outputs two local file paths (submission, answer_key) as JSON.
"""

import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")
TMP_DIR = os.path.join(os.path.dirname(__file__), "..", ".tmp", "submissions")


def get_creds():
    token_path = os.path.join(os.path.dirname(__file__), "..", "token.json")
    from tools.setup_drive import SCOPES
    creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


def download_file(drive, file_id: str, dest_path: str):
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    request = drive.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    with open(dest_path, "wb") as f:
        f.write(buf.getvalue())


def find_answer_key(drive, keys_folder_id: str, asgn_type: str, asgn_code: str) -> str:
    """
    Search answer_keys/ folder for a file matching {TYPE}_{CODE}_KEY.pdf (case-insensitive).
    Returns the Drive file ID or raises FileNotFoundError.
    """
    expected_name = f"{asgn_type}_{asgn_code}_KEY.pdf"
    query = (
        f"'{keys_folder_id}' in parents and trashed=false "
        f"and mimeType='application/pdf'"
    )
    results = drive.files().list(q=query, fields="files(id,name)").execute()
    for f in results.get("files", []):
        if f["name"].upper() == expected_name.upper():
            return f["id"]

    available = [f["name"] for f in results.get("files", [])]
    raise FileNotFoundError(
        f"Answer key '{expected_name}' not found in answer_keys/. "
        f"Available: {available}"
    )


def main():
    if len(sys.argv) < 2:
        print("Usage: python tools/download_pdf.py '<submission_json>'", file=sys.stderr)
        sys.exit(1)

    load_dotenv(ENV_PATH)
    sub = json.loads(sys.argv[1])

    keys_id = os.getenv("DRIVE_KEYS_ID", "").strip()
    if not keys_id:
        print("DRIVE_KEYS_ID not set. Run tools/setup_drive.py first.", file=sys.stderr)
        sys.exit(1)

    creds = get_creds()
    drive = build("drive", "v3", credentials=creds)

    asgn_type = sub["assignment_type"]
    asgn_code = sub["assignment_code"]
    student_id = sub["student_id"]
    student_name = sub["student_name"].replace(" ", "")

    # Download student submission
    submission_filename = f"{asgn_type}_{asgn_code}_{student_id}_{student_name}.pdf"
    submission_path = os.path.join(TMP_DIR, submission_filename)
    print(f"Downloading submission → {submission_path}", file=sys.stderr)
    download_file(drive, sub["drive_file_id"], submission_path)

    # Download answer key
    key_file_id = find_answer_key(drive, keys_id, asgn_type, asgn_code)
    key_filename = f"{asgn_type}_{asgn_code}_KEY.pdf"
    key_path = os.path.join(TMP_DIR, key_filename)
    print(f"Downloading answer key → {key_path}", file=sys.stderr)
    download_file(drive, key_file_id, key_path)

    result = {
        "submission_path": submission_path,
        "answer_key_path": key_path,
        "student_name": sub["student_name"],
        "student_id": student_id,
        "assignment_type": asgn_type,
        "assignment_code": asgn_code,
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
