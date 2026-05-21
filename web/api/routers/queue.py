"""Approval queue routes."""
from __future__ import annotations

import threading

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    UploadFile,
)

from web.api.deps import (
    get_classroom,
    get_classroom_factory,
    get_course_ids,
    get_drive,
    get_keys_folder_id,
    get_reports_folder_id,
)
from web.api.models import (
    ApproveRequest,
    EvalProgressResponse,
    EvaluateRequest,
    EvaluationStartResponse,
    QueueDetail,
    QueueItem,
    ReprocessRequest,
    SetQuestionStatusRequest,
)
from web.api.services import queue as queue_svc

router = APIRouter(prefix="/api/queue", tags=["queue"])


# ───── helpers ─────

def _resolve_assignment(drive, keys_folder_id: str, coursework_id: str) -> dict:
    entry = queue_svc.get_detail(drive, keys_folder_id, coursework_id)
    if entry is None:
        raise HTTPException(
            status_code=404,
            detail=f"coursework {coursework_id} not found in state",
        )
    return entry


def _max_points_for(entry: dict) -> float | None:
    mp = entry.get("max_points")
    try:
        return float(mp) if mp is not None else None
    except (TypeError, ValueError):
        return None


def _to_detail(state_entry: dict, classroom_data: dict) -> dict:
    """Merge stored AK state with live Classroom data into a QueueDetail payload."""
    return {
        "coursework_id": state_entry.get("coursework_id", ""),
        "course_id": state_entry.get("course_id", ""),
        "assignment_type": state_entry.get("assignment_type", "WA"),
        "assignment_code": state_entry.get("assignment_code", ""),
        "assignment_title": state_entry.get("assignment_title", ""),
        "status": state_entry.get("status", "DETECTED"),
        "submission_count": state_entry.get("submission_count", 0)
        or len(classroom_data.get("submissions") or []),
        "questions_count": state_entry.get("questions_count")
        or len(state_entry.get("questions") or []),
        "flagged_count": sum(
            1
            for s in (state_entry.get("questions_status") or [])
            if s == "needs_rework"
        ),
        "current_otp": state_entry.get("current_otp"),
        "model": state_entry.get("model"),
        "generated_at": state_entry.get("generated_at"),
        "approved_at": state_entry.get("approved_at"),
        "created_at": state_entry.get("created_at"),
        "due_at": classroom_data.get("due_at") or state_entry.get("due_at"),
        "alternate_link": classroom_data.get("alternate_link")
        or state_entry.get("alternate_link"),
        "questions": state_entry.get("questions") or [],
        "questions_status": state_entry.get("questions_status") or [],
        "drive_pdf_id": state_entry.get("drive_pdf_id"),
        "regen_count": int(state_entry.get("regen_count") or 0),
        "description": classroom_data.get("description")
        or state_entry.get("description", ""),
        "materials": classroom_data.get("materials") or state_entry.get("materials", []),
        "submissions": classroom_data.get("submissions") or [],
        "work_type": classroom_data.get("work_type") or state_entry.get("work_type"),
        "max_points": classroom_data.get("max_points") or _max_points_for(state_entry),
        "generation_progress": queue_svc.get_generation_progress(
            state_entry.get("coursework_id", "")
        ),
        "errors": state_entry.get("errors") or [],
        "raw_submission_count": classroom_data.get("raw_submission_count"),
    }


# ───── list + detail ─────

@router.get("", response_model=list[QueueItem])
def list_items(
    classroom=Depends(get_classroom),
    classroom_factory=Depends(get_classroom_factory),
    drive=Depends(get_drive),
    keys_folder_id: str = Depends(get_keys_folder_id),
    course_ids: list[str] = Depends(get_course_ids),
) -> list[QueueItem]:
    rows = queue_svc.list_queue(
        classroom, drive, keys_folder_id, course_ids, classroom_factory
    )
    return [QueueItem.model_validate(r) for r in rows]


@router.get("/{coursework_id}", response_model=QueueDetail)
def get_item(
    coursework_id: str,
    classroom=Depends(get_classroom),
    drive=Depends(get_drive),
    keys_folder_id: str = Depends(get_keys_folder_id),
) -> QueueDetail:
    entry = _resolve_assignment(drive, keys_folder_id, coursework_id)
    course_id = entry.get("course_id", "")
    classroom_data = queue_svc.classroom_detail(classroom, course_id, coursework_id)
    payload = _to_detail({"coursework_id": coursework_id, **entry}, classroom_data)
    return QueueDetail.model_validate(payload)


# ───── evaluation ─────

@router.post("/{coursework_id}/evaluate", response_model=EvaluationStartResponse)
def start_evaluations(
    coursework_id: str,
    body: EvaluateRequest,
    drive=Depends(get_drive),
    keys_folder_id: str = Depends(get_keys_folder_id),
    reports_folder_id: str = Depends(get_reports_folder_id),
) -> EvaluationStartResponse:
    entry = _resolve_assignment(drive, keys_folder_id, coursework_id)
    try:
        out = queue_svc.start_evaluation_job(
            drive=drive,
            reports_folder_id=reports_folder_id,
            course_id=entry.get("course_id", ""),
            coursework_id=coursework_id,
            student_ids=list(body.student_ids or []),
            keys_folder_id=keys_folder_id,
            concurrency=body.concurrency or 3,
            force_reeval=bool(body.force_reeval),
            model=body.model,
            provider=body.provider,
        )
    except queue_svc.BudgetExceeded as exc:
        raise HTTPException(status_code=402, detail=str(exc))
    return EvaluationStartResponse.model_validate(out)


@router.get("/{coursework_id}/evaluations/progress", response_model=EvalProgressResponse)
def get_evaluations_progress(coursework_id: str) -> EvalProgressResponse:
    return EvalProgressResponse(progress=queue_svc.get_eval_progress(coursework_id))


@router.post("/{coursework_id}/evaluations/abort")
def abort_evaluations(coursework_id: str) -> dict[str, bool]:
    queue_svc.abort_evaluations(coursework_id)
    return {"ok": True}


# ───── approve / abort / set status / reprocess / generate / upload ─────

@router.post("/{coursework_id}/approve")
def approve(
    coursework_id: str,
    _body: ApproveRequest | None = None,
    classroom=Depends(get_classroom),
    drive=Depends(get_drive),
    keys_folder_id: str = Depends(get_keys_folder_id),
) -> dict:
    try:
        return queue_svc.approve(drive, keys_folder_id, classroom, coursework_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown coursework {coursework_id}")


@router.post("/{coursework_id}/abort")
def abort(
    coursework_id: str,
    drive=Depends(get_drive),
    keys_folder_id: str = Depends(get_keys_folder_id),
) -> dict[str, bool]:
    try:
        queue_svc.abort_generation(drive, keys_folder_id, coursework_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown coursework {coursework_id}")
    return {"ok": True}


@router.post("/{coursework_id}/questions/{question_number}/status")
def set_question_status(
    coursework_id: str,
    question_number: int,
    body: SetQuestionStatusRequest,
    drive=Depends(get_drive),
    keys_folder_id: str = Depends(get_keys_folder_id),
) -> dict:
    try:
        return queue_svc.set_question_status(
            drive, keys_folder_id, coursework_id, question_number, body.status
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown coursework {coursework_id}")
    except (ValueError, IndexError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{coursework_id}/reprocess")
def reprocess(
    coursework_id: str,
    body: ReprocessRequest,
    background_tasks: BackgroundTasks,
    drive=Depends(get_drive),
    keys_folder_id: str = Depends(get_keys_folder_id),
) -> dict:
    try:
        entry = queue_svc.flag_for_reprocess(
            drive,
            keys_folder_id,
            coursework_id,
            list(body.flagged_question_numbers or []),
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown coursework {coursework_id}")
    queue_svc.start_generation(drive, keys_folder_id, coursework_id, entry)

    def _runner():
        try:
            queue_svc.run_generation_inline(
                course_id=entry.get("course_id", ""),
                coursework_id=coursework_id,
                asgn_type=entry.get("assignment_type", "WA"),
                asgn_code=entry.get("assignment_code", ""),
                asgn_title=entry.get("assignment_title", ""),
                keys_folder_id=keys_folder_id,
            )
        except Exception:
            pass

    threading.Thread(target=_runner, name=f"reprocess-{coursework_id}", daemon=True).start()
    return {"ok": True, "regen_count": entry.get("regen_count", 0)}


@router.post("/{coursework_id}/generate")
def generate(
    coursework_id: str,
    background_tasks: BackgroundTasks,
    classroom=Depends(get_classroom),
    classroom_factory=Depends(get_classroom_factory),
    drive=Depends(get_drive),
    keys_folder_id: str = Depends(get_keys_folder_id),
    course_ids: list[str] = Depends(get_course_ids),
) -> dict:
    queue = queue_svc.list_queue(
        classroom, drive, keys_folder_id, course_ids, classroom_factory
    )
    row = next((q for q in queue if q.get("coursework_id") == coursework_id), None)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"coursework {coursework_id} not found in any configured course",
        )
    summary = {
        "coursework_id": coursework_id,
        "course_id": row.get("course_id", ""),
        "assignment_type": row.get("assignment_type", "WA"),
        "assignment_code": row.get("assignment_code", ""),
        "assignment_title": row.get("assignment_title", ""),
    }
    queue_svc.start_generation(drive, keys_folder_id, coursework_id, summary)

    def _runner():
        try:
            queue_svc.run_generation_inline(
                course_id=summary["course_id"],
                coursework_id=coursework_id,
                asgn_type=summary["assignment_type"],
                asgn_code=summary["assignment_code"],
                asgn_title=summary["assignment_title"],
                keys_folder_id=keys_folder_id,
            )
        except Exception:
            pass

    threading.Thread(target=_runner, name=f"generate-{coursework_id}", daemon=True).start()
    return {"ok": True, "status": "GENERATING"}


@router.post("/{coursework_id}/upload-key")
def upload_key(
    coursework_id: str,
    file: UploadFile = File(...),
    classroom=Depends(get_classroom),
    classroom_factory=Depends(get_classroom_factory),
    drive=Depends(get_drive),
    keys_folder_id: str = Depends(get_keys_folder_id),
    course_ids: list[str] = Depends(get_course_ids),
) -> dict:
    if (file.content_type or "").lower() not in ("application/pdf",):
        raise HTTPException(status_code=400, detail="upload must be application/pdf")
    pdf_bytes = file.file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="empty PDF upload")

    queue = queue_svc.list_queue(
        classroom, drive, keys_folder_id, course_ids, classroom_factory
    )
    row = next((q for q in queue if q.get("coursework_id") == coursework_id), None)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"coursework {coursework_id} not in any configured course",
        )
    entry = queue_svc.upload_manual_answer_key(
        drive=drive,
        classroom=classroom,
        keys_folder_id=keys_folder_id,
        course_id=row.get("course_id", ""),
        coursework_id=coursework_id,
        pdf_bytes=pdf_bytes,
        asgn_type=row.get("assignment_type", "WA"),
        asgn_code=row.get("assignment_code", ""),
        asgn_title=row.get("assignment_title", ""),
    )
    return {"ok": True, "drive_pdf_id": entry.get("drive_pdf_id")}


# ───── per-student link / unlink ─────

@router.post("/{coursework_id}/submissions/{student_id}/link")
def link_one(
    coursework_id: str,
    student_id: str,
    classroom=Depends(get_classroom),
    drive=Depends(get_drive),
    keys_folder_id: str = Depends(get_keys_folder_id),
    reports_folder_id: str = Depends(get_reports_folder_id),
) -> dict:
    entry = _resolve_assignment(drive, keys_folder_id, coursework_id)
    try:
        return queue_svc.link_submission(
            classroom=classroom,
            drive=drive,
            reports_folder_id=reports_folder_id,
            course_id=entry.get("course_id", ""),
            coursework_id=coursework_id,
            student_id=student_id,
            assignment_type=entry.get("assignment_type", "WA"),
            assignment_code=entry.get("assignment_code", ""),
            max_points=_max_points_for(entry),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{coursework_id}/submissions/{student_id}/unlink")
def unlink_one(
    coursework_id: str,
    student_id: str,
    classroom=Depends(get_classroom),
    drive=Depends(get_drive),
    keys_folder_id: str = Depends(get_keys_folder_id),
    reports_folder_id: str = Depends(get_reports_folder_id),
) -> dict:
    entry = _resolve_assignment(drive, keys_folder_id, coursework_id)
    try:
        return queue_svc.unlink_submission(
            classroom=classroom,
            drive=drive,
            reports_folder_id=reports_folder_id,
            course_id=entry.get("course_id", ""),
            coursework_id=coursework_id,
            student_id=student_id,
            assignment_type=entry.get("assignment_type", "WA"),
            assignment_code=entry.get("assignment_code", ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ───── bulk link / unlink + progress ─────

@router.post("/{coursework_id}/link-all-graded")
def link_all_graded(
    coursework_id: str,
    classroom=Depends(get_classroom),
    drive=Depends(get_drive),
    keys_folder_id: str = Depends(get_keys_folder_id),
    reports_folder_id: str = Depends(get_reports_folder_id),
) -> dict:
    entry = _resolve_assignment(drive, keys_folder_id, coursework_id)
    return queue_svc.bulk_link_all_graded(
        classroom=classroom,
        drive=drive,
        reports_folder_id=reports_folder_id,
        course_id=entry.get("course_id", ""),
        coursework_id=coursework_id,
        assignment_type=entry.get("assignment_type", "WA"),
        assignment_code=entry.get("assignment_code", ""),
        max_points=_max_points_for(entry),
    )


@router.post("/{coursework_id}/unlink-all-linked")
def unlink_all_linked(
    coursework_id: str,
    classroom=Depends(get_classroom),
    drive=Depends(get_drive),
    keys_folder_id: str = Depends(get_keys_folder_id),
    reports_folder_id: str = Depends(get_reports_folder_id),
) -> dict:
    entry = _resolve_assignment(drive, keys_folder_id, coursework_id)
    return queue_svc.bulk_unlink_all_linked(
        classroom=classroom,
        drive=drive,
        reports_folder_id=reports_folder_id,
        course_id=entry.get("course_id", ""),
        coursework_id=coursework_id,
        assignment_type=entry.get("assignment_type", "WA"),
        assignment_code=entry.get("assignment_code", ""),
    )


@router.get("/{coursework_id}/bulk-progress")
def bulk_progress(coursework_id: str) -> dict:
    return queue_svc.get_bulk_job(coursework_id) or {}
