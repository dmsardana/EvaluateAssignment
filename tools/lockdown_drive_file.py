"""
Lock a Drive file into strict view-only mode.

Setting ``copyRequiresWriterPermission=True`` and
``viewersCanCopyContent=False`` on the file metadata prevents readers
from downloading, copying, or printing the content via the Drive UI.

This is best-effort defence in depth — a determined viewer can still
screenshot. But it satisfies the "view only" requirement when sharing
graded report PDFs with students.
"""
from __future__ import annotations

from googleapiclient.errors import HttpError

_LOCKDOWN_BODY: dict = {
    "copyRequiresWriterPermission": True,
    "viewersCanCopyContent": False,
    "writersCanShare": False,
}


def apply_view_lockdown(drive, file_id: str) -> None:
    drive.files().update(fileId=file_id, body=_LOCKDOWN_BODY).execute()


def verify_view_lockdown(drive, file_id: str) -> None:
    meta = (
        drive.files()
        .get(
            fileId=file_id,
            fields=(
                "copyRequiresWriterPermission,"
                "viewersCanCopyContent,"
                "writersCanShare"
            ),
        )
        .execute()
    )
    failures: list[str] = []
    if not meta.get("copyRequiresWriterPermission"):
        failures.append("copyRequiresWriterPermission != True")
    if meta.get("viewersCanCopyContent"):
        failures.append("viewersCanCopyContent != False")
    if meta.get("writersCanShare"):
        failures.append("writersCanShare != False")
    if failures:
        raise RuntimeError(
            f"Drive lockdown verification failed for {file_id}: "
            + ", ".join(failures)
        )


def ensure_view_lockdown(drive, file_id: str) -> None:
    """Apply lockdown + verify it took. Idempotent."""
    try:
        apply_view_lockdown(drive, file_id)
    except HttpError as e:
        raise RuntimeError(
            f"Drive lockdown apply failed for {file_id}: {e}"
        ) from e
    verify_view_lockdown(drive, file_id)


def is_drive_404(err: object) -> bool:
    if not isinstance(err, HttpError):
        return False
    resp = getattr(err, "resp", None)
    return getattr(resp, "status", None) == 404
