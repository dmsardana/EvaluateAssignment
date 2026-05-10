"""
Gmail send + read helpers for the answer-key review workflow.
- send_review_email: sends HTML email with PDF attachment + OTP
- search_replies: finds replies to review-request emails by OTP / threadId
"""

import base64
import os
import sys
from email.message import EmailMessage

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


def get_creds():
    token_path = os.path.join(os.path.dirname(__file__), "..", "token.json")
    from tools.setup_drive import SCOPES
    creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


def gmail_service():
    return build("gmail", "v1", credentials=get_creds())


def send_review_email(
    to_addr: str,
    subject: str,
    body_text: str,
    body_html: str,
    attachment_path: str,
    attachment_name: str,
) -> dict:
    """Returns the sent message resource (includes id, threadId)."""
    msg = EmailMessage()
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body_text)
    msg.add_alternative(body_html, subtype="html")

    with open(attachment_path, "rb") as f:
        data = f.read()
    msg.add_attachment(
        data,
        maintype="application",
        subtype="pdf",
        filename=attachment_name,
    )

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    service = gmail_service()
    sent = service.users().messages().send(
        userId="me", body={"raw": raw}
    ).execute()
    return sent


def list_replies_by_thread(thread_id: str) -> list[dict]:
    """Return all messages in a thread sorted by internalDate ascending."""
    service = gmail_service()
    thread = service.users().threads().get(
        userId="me", id=thread_id, format="full"
    ).execute()
    messages = thread.get("messages", [])
    messages.sort(key=lambda m: int(m.get("internalDate", "0")))
    return messages


def search_replies_with_otp(otp: str) -> list[dict]:
    """Find recent inbox messages whose body or subject contains the OTP."""
    service = gmail_service()
    q = f'in:inbox newer_than:7d "{otp}"'
    resp = service.users().messages().list(userId="me", q=q, maxResults=20).execute()
    out = []
    for ref in resp.get("messages", []):
        msg = service.users().messages().get(
            userId="me", id=ref["id"], format="full"
        ).execute()
        out.append(msg)
    return out


def extract_plain_text(message: dict) -> str:
    """Walk the message payload and return concatenated plain-text bodies."""
    parts = []

    def walk(payload):
        mime = payload.get("mimeType", "")
        if mime == "text/plain":
            data = payload.get("body", {}).get("data")
            if data:
                parts.append(base64.urlsafe_b64decode(data + "===").decode("utf-8", errors="replace"))
        elif mime.startswith("multipart/"):
            for sub in payload.get("parts", []):
                walk(sub)
        else:
            data = payload.get("body", {}).get("data")
            if data:
                parts.append(base64.urlsafe_b64decode(data + "===").decode("utf-8", errors="replace"))

    walk(message.get("payload", {}))
    return "\n".join(parts)


def get_message_subject(message: dict) -> str:
    for h in message.get("payload", {}).get("headers", []):
        if h.get("name", "").lower() == "subject":
            return h.get("value", "")
    return ""
