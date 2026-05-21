"""Student roster — Classroom identity + editable display name / email /
mobile persisted in Postgres."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from web.api.deps import (
    get_classroom,
    get_classroom_factory,
    get_course_ids,
    get_drive,
    get_reports_folder_id,
)
from web.api.models import StudentProfile, StudentProfilePatch
from web.api.services import queue as queue_svc

router = APIRouter(prefix="/api", tags=["students"])


@router.get("/students", response_model=list[StudentProfile])
def list_students(
    classroom=Depends(get_classroom),
    classroom_factory=Depends(get_classroom_factory),
    drive=Depends(get_drive),
    reports_folder_id: str = Depends(get_reports_folder_id),
    course_ids: list[str] = Depends(get_course_ids),
) -> list[StudentProfile]:
    rows = queue_svc.list_students_with_profiles(
        classroom=classroom,
        drive=drive,
        reports_folder_id=reports_folder_id,
        course_ids=course_ids,
        classroom_factory=classroom_factory,
    )
    return [StudentProfile.model_validate(r) for r in rows]


@router.put("/students/{student_id}", response_model=StudentProfile)
def update_student(
    student_id: str,
    patch: StudentProfilePatch,
    drive=Depends(get_drive),
    reports_folder_id: str = Depends(get_reports_folder_id),
) -> StudentProfile:
    sid = (student_id or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="student_id is required")
    try:
        row = queue_svc.upsert_student_profile(
            drive=drive,
            reports_folder_id=reports_folder_id,
            student_id=sid,
            display_name=patch.display_name,
            email=patch.email,
            mobile=patch.mobile,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return StudentProfile.model_validate(row)
