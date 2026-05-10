"""
Upload a compiled report PDF to the Drive reports/ folder.

Usage:
    python tools/upload_report.py <pdf_path>

Prints the uploaded file's Drive ID.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")


def get_creds():
    token_path = os.path.join(os.path.dirname(__file__), "..", "token.json")
    from tools.setup_drive import SCOPES
    creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


def upload(pdf_path: str, reports_folder_id: str) -> str:
    creds = get_creds()
    drive = build("drive", "v3", credentials=creds)

    filename = os.path.basename(pdf_path)

    # Remove stale file with same name if it exists
    query = f"name='{filename}' and '{reports_folder_id}' in parents and trashed=false"
    existing = drive.files().list(q=query, fields="files(id)").execute().get("files", [])
    for f in existing:
        drive.files().delete(fileId=f["id"]).execute()

    file_metadata = {
        "name": filename,
        "parents": [reports_folder_id],
    }
    media = MediaFileUpload(pdf_path, mimetype="application/pdf", resumable=True)
    uploaded = drive.files().create(
        body=file_metadata, media_body=media, fields="id,webViewLink"
    ).execute()

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
