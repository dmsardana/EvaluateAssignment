"""Recent graded results across all courses — a flat list for the Wire view."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from web.api.deps import get_drive, get_reports_folder_id
from web.api.models import WireItem
from web.api.services import queue as queue_svc

router = APIRouter(prefix="/api", tags=["wire"])


@router.get("/wire", response_model=list[WireItem])
def list_wire(
    limit: int = Query(default=50, ge=1, le=500),
    drive=Depends(get_drive),
    reports_folder_id: str = Depends(get_reports_folder_id),
) -> list[WireItem]:
    rows = queue_svc.list_wire(
        drive=drive,
        reports_folder_id=reports_folder_id,
        limit=limit,
    )
    return [WireItem.model_validate(r) for r in rows]
