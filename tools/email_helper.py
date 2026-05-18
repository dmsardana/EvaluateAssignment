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


def gmail_service():
    from web.api.services.credentials import REGISTRY
    return REGISTRY.get("google_oauth").get_gmail()


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


def send_simple_email(
    to_addr: str,
    subject: str,
    body_text: str,
    body_html: str,
) -> dict:
    """Send an email without attachments. Used for approval-confirmation emails
    that link to AK PDF in Drive rather than attaching it."""
    msg = EmailMessage()
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body_text)
    msg.add_alternative(body_html, subtype="html")

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    service = gmail_service()
    return service.users().messages().send(
        userId="me", body={"raw": raw}
    ).execute()


def send_email(to: str, subject: str, body: str) -> dict:
    """Adapter for plain-text ops alerts.

    Bridges StatusEdgeNotifier (uses to/subject/body kwargs) to
    send_simple_email (which requires body_html). The body is plain text;
    we pass it as-is to both slots.
    """
    return send_simple_email(
        to_addr=to,
        subject=subject,
        body_text=body,
        body_html=f"<pre>{body}</pre>",
    )


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
