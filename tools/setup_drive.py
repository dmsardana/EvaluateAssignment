"""
One-time setup: OAuth authentication, Drive folder discovery/creation,
Classroom course listing. Writes folder IDs and course IDs back to .env.

Run once before using the pipeline:
    python tools/setup_drive.py
"""

import os
# Tolerate Google reordering / merging scopes during the consent flow —
# oauthlib otherwise raises a strict warning that aborts the exchange.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

from dotenv import load_dotenv, set_key
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.students.readonly",
    "https://www.googleapis.com/auth/classroom.student-submissions.students.readonly",
    "https://www.googleapis.com/auth/classroom.rosters.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]

ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")


def authenticate():
    creds = None
    token_path = os.path.join(os.path.dirname(__file__), "..", "token.json")
    creds_path = os.path.join(os.path.dirname(__file__), "..", "credentials.json")

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(creds_path):
                raise FileNotFoundError(
                    "credentials.json not found. Download it from Google Cloud Console "
                    "(APIs & Services → Credentials → OAuth 2.0 Client)."
                )
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())
        print("✓ token.json saved")

    return creds


def find_or_create_folder(drive, parent_id, name):
    query = (
        f"name='{name}' and '{parent_id}' in parents "
        f"and mimeType='application/vnd.google-apps.folder' and trashed=false"
    )
    results = drive.files().list(q=query, fields="files(id,name)").execute()
    files = results.get("files", [])
    if files:
        return files[0]["id"]

    metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    folder = drive.files().create(body=metadata, fields="id").execute()
    print(f"  Created folder '{name}'")
    return folder["id"]


def list_courses(classroom):
    courses = []
    page_token = None
    while True:
        resp = classroom.courses().list(
            courseStates=["ACTIVE"], pageToken=page_token, pageSize=50
        ).execute()
        courses.extend(resp.get("courses", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return courses


def main():
    load_dotenv(ENV_PATH)
    root_id = os.getenv("DRIVE_ROOT_ID", "").strip()
    if not root_id:
        raise ValueError("DRIVE_ROOT_ID is not set in .env")

    print("Authenticating with Google…")
    creds = authenticate()

    drive = build("drive", "v3", credentials=creds)
    classroom = build("classroom", "v1", credentials=creds)

    print("\nSetting up Drive folders…")
    keys_id = find_or_create_folder(drive, root_id, "answer_keys")
    reports_id = find_or_create_folder(drive, root_id, "reports")

    set_key(ENV_PATH, "DRIVE_KEYS_ID", keys_id)
    set_key(ENV_PATH, "DRIVE_REPORTS_ID", reports_id)
    print(f"  answer_keys/ → {keys_id}")
    print(f"  reports/     → {reports_id}")

    print("\nFetching Google Classroom courses…")
    courses = list_courses(classroom)
    if not courses:
        print("  No active courses found.")
    else:
        print(f"  Found {len(courses)} active course(s):")
        for c in courses:
            print(f"    [{c['id']}] {c['name']}")

        course_ids = ",".join(c["id"] for c in courses)
        set_key(ENV_PATH, "CLASSROOM_COURSE_IDS", course_ids)
        print(f"\n  CLASSROOM_COURSE_IDS set to: {course_ids}")
        print("  Edit .env to keep only the relevant course IDs if needed.")

    print("\n✓ Setup complete. .env updated.")


if __name__ == "__main__":
    main()
