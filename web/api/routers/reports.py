"""All graded reports — one row per (student × assignment)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from web.api.deps import (
    get_classroom,
    get_course_ids,
    get_drive,
    get_keys_folder_id,
    get_reports_folder_id,
)
from web.api.models import ReportRow
from web.api.services import queue as queue_svc

router = APIRouter(prefix="/api", tags=["reports"])


@router.get("/reports", response_model=list[ReportRow])
def list_reports(
    classroom=Depends(get_classroom),
    drive=Depends(get_drive),
    keys_folder_id: str = Depends(get_keys_folder_id),
    reports_folder_id: str = Depends(get_reports_folder_id),
    course_ids: list[str] = Depends(get_course_ids),
) -> list[ReportRow]:
    rows = queue_svc.list_all_reports(
        classroom=classroom,
        drive=drive,
        keys_folder_id=keys_folder_id,
        reports_folder_id=reports_folder_id,
        course_ids=course_ids,
    )
    return [ReportRow.model_validate(r) for r in rows]
