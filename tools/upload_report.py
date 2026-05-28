"""
Upload a compiled report PDF to the Drive reports/ folder.

Usage:
    python tools/upload_report.py <pdf_path>

Prints the uploaded file's Drive ID.
"""

import os
import socket
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

import httplib2

_TRANSIENT_NETWORK_EXC = (
    socket.gaierror,
    OSError,
    TimeoutError,
    httplib2.error.ServerNotFoundError,
    ConnectionError,
)


def _with_retry(fn, *, retries: int = 5, base_delay: float = 2.0):
    """Run fn() with exponential backoff on transient network errors.
    DNS/route failures and 5xx HttpErrors are retried; 4xx HttpErrors are not."""
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            return fn()
        except HttpError as exc:
            status = getattr(exc.resp, "status", 0)
            if status and 500 <= status < 600 and attempt < retries - 1:
                last_exc = exc
                time.sleep(base_delay * (2 ** attempt))
                continue
            raise
        except _TRANSIENT_NETWORK_EXC as exc:
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(base_delay * (2 ** attempt))
                continue
            raise
    if last_exc:
        raise last_exc
    return None

ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")


def get_creds():
    token_path = os.path.join(os.path.dirname(__file__), "..", "token.json")
    from tools.setup_drive import SCOPES
    creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


def upload(pdf_path: str, reports_folder_id: str) -> str:
    creds = _with_retry(get_creds)
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)

    filename = os.path.basename(pdf_path)

    query = f"name='{filename}' and '{reports_folder_id}' in parents and trashed=false"
    existing = _with_retry(
        lambda: drive.files().list(q=query, fields="files(id)").execute()
    ).get("files", [])
    for f in existing:
        _with_retry(lambda fid=f["id"]: drive.files().delete(fileId=fid).execute())

    file_metadata = {"name": filename, "parents": [reports_folder_id]}
    # MediaFileUpload must be re-created per retry — its underlying file
    # handle gets consumed by a failed resumable upload.
    def _do_create():
        media = MediaFileUpload(pdf_path, mimetype="application/pdf", resumable=True)
        return drive.files().create(
            body=file_metadata, media_body=media, fields="id,webViewLink"
        ).execute()

    uploaded = _with_retry(_do_create)

    print(f"Uploaded '{filename}' → {uploaded.get('webViewLink', uploaded['id'])}", file=sys.stderr)
    return uploaded["id"]


def main():
    if len(sys.argv) < 2:
        print("Usage: python tools/upload_report.py <pdf_path>", file=sys.stderr)
        sys.exit(1)

    load_dotenv(ENV_PATH)
    pdf_path = sys.argv[1]
    reports_id = os.getenv("DRIVE_REPORTS_ID", "").strip()
    if not reports_id:
        print("DRIVE_REPORTS_ID not set. Run tools/setup_drive.py first.", file=sys.stderr)
        sys.exit(1)

    file_id = upload(pdf_path, reports_id)
    print(file_id)


if __name__ == "__main__":
    main()
