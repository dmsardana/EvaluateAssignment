"""Pivoted student × assignment scores matrix for the Scores page."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from web.api.deps import (
    get_classroom,
    get_classroom_factory,
    get_course_ids,
    get_drive,
    get_keys_folder_id,
    get_reports_folder_id,
)
from web.api.models import ScoreMatrixResponse
from web.api.services import queue as queue_svc

router = APIRouter(prefix="/api", tags=["scores"])


@router.get("/scores-matrix", response_model=ScoreMatrixResponse)
def get_scores_matrix(
    classroom=Depends(get_classroom),
    classroom_factory=Depends(get_classroom_factory),
    drive=Depends(get_drive),
    keys_folder_id: str = Depends(get_keys_folder_id),
    reports_folder_id: str = Depends(get_reports_folder_id),
    course_ids: list[str] = Depends(get_course_ids),
) -> ScoreMatrixResponse:
    payload = queue_svc.score_matrix(
        classroom=classroom,
        drive=drive,
        keys_folder_id=keys_folder_id,
        reports_folder_id=reports_folder_id,
        course_ids=course_ids,
        classroom_factory=classroom_factory,
    )
    return ScoreMatrixResponse.model_validate(payload)
