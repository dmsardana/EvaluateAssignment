"""
Link a graded report PDF back to the student's Classroom submission +
email the student a read-only view link.

Two-step flow:

1. **Share** the PDF with the student's email at role=reader. Drive
   enforces this via ``permissions.create``. The file is locked into
   view-only mode via :mod:`tools.lockdown_drive_file` (no copy / no
   print / no download).
2. **Email** the student a short note with the Drive view URL. Sent
   via the same Gmail service used by the rest of the pipeline.

Unlink reverses step 1 (deletes the Drive permission). The student's
score on Classroom is not affected.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from email.message import EmailMessage

from googleapiclient.errors import HttpError

from tools.lockdown_drive_file import ensure_view_lockdown


WORKSPACE_WHITELIST_MSG = (
    "Drive is refusing to share with external emails. Check your Google "
    "Workspace sharing policy or add the student's email to the allowlist."
)


class StudentEmailMissing(Exception):
    """Raised when we can't find or were not given the student's email."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_status(e: object, status: int) -> bool:
    resp = getattr(e, "resp", None)
    return getattr(resp, "status", None) == status


def _is_403(e: object) -> bool:
    return _is_status(e, 403)


def _is_400(e: object) -> bool:
    return _is_status(e, 400)


def _is_404(e: object) -> bool:
    return _is_status(e, 404)


def _is_409(e: object) -> bool:
    return _is_status(e, 409)


def _body_text(e: object) -> str:
    if not hasattr(e, "content"):
        return ""
    try:
        return e.content.decode("utf-8", "replace")
    except Exception:
        return ""


def _explain_403(e: object) -> str:
    body = _body_text(e)
    return f"{WORKSPACE_WHITELIST_MSG}\n\n{body}".strip()


def _explain_drive_share_400(e: object, email: str) -> str:
    body = _body_text(e).lower()
    if "invalid" in body and "email" in body:
        return f"Drive rejected the email '{email}' as invalid."
    return f"Drive permissions.create returned 400 for '{email}'."


def _resolve_student_email(classroom, student_id: str, student_name: str) -> str:
    """Best-effort lookup via Classroom userProfiles."""
    try:
        prof = classroom.userProfiles().get(userId=student_id).execute()
    except HttpError as e:
        if _is_403(e):
            raise RuntimeError(_explain_403(e)) from e
        raise StudentEmailMissing(
            f"Couldn't look up Classroom profile for {student_name} ({student_id})"
        ) from e
    email = (prof.get("emailAddress") or "").strip()
    if not email:
        raise StudentEmailMissing(
            f"Classroom returned no email for {student_name} ({student_id})"
        )
    return email


def _file_owner_email(drive, drive_file_id: str) -> str:
    try:
        meta = (
            drive.files()
            .get(fileId=drive_file_id, fields="owners(emailAddress)")
            .execute()
        )
    except HttpError:
        return ""
    owners = meta.get("owners") or []
    if not owners:
        return ""
    return (owners[0].get("emailAddress") or "").lower()


def _share_pdf_with_email(drive, drive_file_id: str, email: str) -> str:
    """Return the new permissionId. If the email already has access,
    return the existing permissionId."""
    clean = (email or "").strip().lower()
    if not clean:
        raise ValueError("email is required to share the PDF")
    try:
        perm = (
            drive.permissions()
            .create(
                fileId=drive_file_id,
                body={"type": "user", "role": "reader", "emailAddress": clean},
                sendNotificationEmail=False,
                fields="id",
            )
            .execute()
        )
        return perm["id"]
    except HttpError as e:
        if _is_400(e):
            raise RuntimeError(_explain_drive_share_400(e, clean)) from e
        if _is_409(e):
            existing = (
                drive.permissions()
                .list(fileId=drive_file_id, fields="permissions(id,emailAddress)")
                .execute()
            )
            for p in existing.get("permissions", []):
                if (p.get("emailAddress") or "").lower() == clean:
                    return p["id"]
            raise RuntimeError(
                f"Drive returned 409 sharing with {clean}, "
                "but no matching permission found"
            ) from e
        if _is_403(e):
            raise RuntimeError(_explain_403(e)) from e
        raise


def _send_share_email(
    gmail,
    to_email: str,
    student_name: str,
    assignment_title: str,
    percentage: float | None,
    drive_view_url: str,
    teacher_email: str | None = None,
) -> None:
    first = (student_name or "").split()[0] if student_name else "Student"
    score = (
        f"{percentage:.1f}%"
        if isinstance(percentage, (int, float))
        else "ready to view"
    )
    subject = f"Your evaluation report — {assignment_title}"
    plain = (
        f"Hi {first},\n\n"
        f"Your evaluation for '{assignment_title}' is {score}. "
        "You can open the read-only report here:\n\n"
        f"{drive_view_url}\n\n"
        "The link only works for this email; downloading and printing are disabled.\n\n"
        "— thinkingSouls"
    )
    html = (
        f"<p>Hi {first},</p>"
        f"<p>Your evaluation for <em>{assignment_title}</em> is "
        f"<strong>{score}</strong>. You can open the read-only report here:</p>"
        f'<p><a href="{drive_view_url}">Open report</a></p>'
        f'<p style="color:#666;font-size:12px">The link only works for this email; '
        "downloading and printing are disabled.</p>"
    )
    msg = EmailMessage()
    msg["To"] = to_email
    if teacher_email:
        msg["Bcc"] = teacher_email
    msg["Subject"] = subject
    msg.set_content(plain)
    msg.add_alternative(html, subtype="html")
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    try:
        gmail.users().messages().send(userId="me", body={"raw": raw}).execute()
    except HttpError as e:
        if _is_403(e):
            raise RuntimeError(_explain_403(e)) from e
        raise


def link_report_to_submission(
    classroom,
    drive,
    gmail,
    course_id: str,
    coursework_id: str,
    submission_id: str | None,
    drive_file_id: str,
    student_id: str,
    student_name: str,
    assignment_title: str,
    percentage: float | None,
    drive_view_url: str,
    student_email: str | None = None,
    assigned_grade: float | None = None,
) -> dict:
    """Lock the PDF, share it with the student, email them a link.

    Returns ``{shared_with_email, drive_permission_id, linked_at}``.
    """
    ensure_view_lockdown(drive, drive_file_id)
    email = (student_email or "").strip()
    if not email:
        email = _resolve_student_email(classroom, student_id, student_name)
    permission_id = _share_pdf_with_email(drive, drive_file_id, email)
    _send_share_email(
        gmail,
        to_email=email,
        student_name=student_name,
        assignment_title=assignment_title,
        percentage=percentage,
        drive_view_url=drive_view_url,
    )
    return {
        "shared_with_email": email,
        "drive_permission_id": permission_id,
        "linked_at": _now_iso(),
    }


def unlink_report_from_submission(
    classroom,
    drive,
    course_id: str,
    coursework_id: str,
    submission_id: str | None,
    drive_file_id: str,
    drive_permission_id: str | None,
) -> dict:
    """Revoke the student's read access to the PDF. Idempotent for 404."""
    if not drive_permission_id:
        return {"unlinked_at": _now_iso()}
    try:
        drive.permissions().delete(
            fileId=drive_file_id, permissionId=drive_permission_id
        ).execute()
    except HttpError as e:
        if _is_404(e):
            pass
        elif _is_403(e):
            raise RuntimeError(_explain_403(e)) from e
        else:
            raise
    return {"unlinked_at": _now_iso()}
