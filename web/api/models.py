"""
Pydantic response models for the API.

Mirror the existing pipeline state and scores.csv schemas one-for-one —
see `tools/review_state.py` and `tools/track_scores.py` for the source
of truth.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ───────── Enums ─────────

Status = Literal[
    "DETECTED",
    "GENERATING",
    "PENDING_REVIEW",
    "NEEDS_REGEN",
    "APPROVED",
    "SHARED",
]

QStatus = Literal["pending", "approved", "needs_rework"]

Tier = Literal["WA", "QA", "AA", "ZA"]

Band = Literal["TRBLZ", "QUALIF", "DEVLP", "F-GAPS"]

MaterialKind = Literal["drive_file", "link", "youtube", "form"]


# ───────── Question / AK pieces ─────────

class Question(BaseModel):
    """A single question in the answer key."""

    number: int | str
    question_text: str
    difficulty: Optional[str] = None
    approach: Optional[str] = None
    solution: Optional[str] = None
    final_answer: Optional[str] = None
    concise: Optional[str] = None
    common_mistakes: Optional[str] = None


class Material(BaseModel):
    kind: MaterialKind
    title: str
    url: Optional[str] = None
    drive_id: Optional[str] = None
    thumbnail_url: Optional[str] = None


class SubmissionAttachment(BaseModel):
    title: str
    url: Optional[str] = None
    drive_id: Optional[str] = None


# ───────── Queue list view ─────────

class QueueItem(BaseModel):
    """One row in the Approval Queue list."""

    coursework_id: str
    course_id: str
    assignment_type: Tier
    assignment_code: str
    assignment_title: str
    status: Status
    submission_count: int = 0
    questions_count: int = 0
    flagged_count: int = 0
    current_otp: Optional[str] = None
    model: Optional[str] = None
    generated_at: Optional[str] = None
    approved_at: Optional[str] = None
    created_at: Optional[str] = None
    due_at: Optional[str] = None
    alternate_link: Optional[str] = None


# ───────── Submissions on the detail view ─────────

class Submission(BaseModel):
    """One student submission in the drawer view."""

    student_id: str
    student_name: str
    submission_id: Optional[str] = None
    state: str
    submitted_at: str
    late: bool = False
    attachments: list[SubmissionAttachment] = Field(default_factory=list)
    alternate_link: Optional[str] = None
    graded_percentage: Optional[float] = None
    graded_earned: Optional[float] = None
    graded_max: Optional[float] = None
    graded_at: Optional[str] = None
    report_drive_id: Optional[str] = None
    report_url: Optional[str] = None
    linked_at: Optional[str] = None
    unlinked_at: Optional[str] = None


# ───────── Generation progress ─────────

class GenerationProgress(BaseModel):
    """In-flight progress info for a GENERATING coursework. Populated only
    when the API server is actively running an AK generation."""

    stage: str
    label: str
    percent: int
    started_at: str
    updated_at: str


class QueueDetail(QueueItem):
    """Drawer view — adds full question list and live Classroom data."""

    questions: list[Question] = Field(default_factory=list)
    questions_status: list[QStatus] = Field(default_factory=list)
    drive_pdf_id: Optional[str] = None
    regen_count: int = 0
    description: str = ""
    materials: list[Material] = Field(default_factory=list)
    submissions: list[Submission] = Field(default_factory=list)
    work_type: Optional[str] = None
    max_points: Optional[float] = None
    generation_progress: Optional[GenerationProgress] = None
    errors: list[dict] = Field(default_factory=list)
    raw_submission_count: Optional[int] = None


# ───────── Approve / reprocess / status / evaluate ─────────

class ApproveRequest(BaseModel):
    """Empty for now — kept as a body schema so future fields can land."""


class ReprocessRequest(BaseModel):
    flagged_question_numbers: list[int]


class SetQuestionStatusRequest(BaseModel):
    status: QStatus


class EvaluateRequest(BaseModel):
    """Kick off per-student evaluations. Server runs them in parallel
    according to `concurrency` (default 3, max 10).

    `force_reeval=True` bypasses the evaluation-JSON cache so Claude is
    re-called (spends ~$0.50/student). Default False uses the cache when
    present, which makes regenerating already-graded reports free
    (LaTeX re-render only).
    """

    student_ids: list[str]
    concurrency: Optional[int] = 3
    force_reeval: Optional[bool] = False
    model: Optional[str] = None

    @field_validator("concurrency")
    @classmethod
    def _clamp_concurrency(cls, v: int | None) -> int | None:
        if v is None:
            return None
        return max(1, min(10, int(v)))


class EvaluationStartResponse(BaseModel):
    job_started: bool
    student_count: int
    estimated_cost_usd: float
    available_usd: float
    concurrency: int
    cached_count: int
    fresh_count: int


class EvalProgressEntry(BaseModel):
    coursework_id: str
    student_id: str
    stage: str
    label: str
    percent: int
    status: str
    started_at: str
    updated_at: str
    percentage: Optional[float] = None
    report_drive_id: Optional[str] = None
    report_url: Optional[str] = None
    error: Optional[str] = None
    completed_at: Optional[str] = None
    duration_seconds: Optional[int] = None


class EvalProgressResponse(BaseModel):
    progress: dict[str, EvalProgressEntry] = Field(default_factory=dict)


# ───────── Students + courses ─────────

class CourseEnrolment(BaseModel):
    """A class/group the student is enrolled in. Sourced from Google
    Classroom (course name + section + enrollment code). Shown as a chip
    in the Students table so the teacher can identify the group at a
    glance — corresponds to the user's 'Classroom Code'."""

    course_id: str
    name: str
    section: Optional[str] = ""
    enrollment_code: Optional[str] = ""
    label: str


class StudentProfile(BaseModel):
    """One row in the Students page. Identity comes from the live Classroom
    roster (student_id + student_name); display_name + email + mobile are
    persisted in students.csv on Drive and Postgres."""

    student_id: str
    student_name: str
    display_name: Optional[str] = ""
    email: Optional[str] = ""
    mobile: Optional[str] = ""
    updated_at: Optional[str] = ""
    in_roster: bool = True
    courses: list[CourseEnrolment] = Field(default_factory=list)


class StudentProfilePatch(BaseModel):
    """Editable fields on the Students page. None means 'leave as-is'."""

    student_name: Optional[str] = None
    display_name: Optional[str] = None
    email: Optional[str] = None
    mobile: Optional[str] = None


# ───────── Scores matrix ─────────

class ScoreMatrixAssignment(BaseModel):
    """Column in the Score Matrix view — one per (type, code)."""

    key: str
    assignment_type: Tier
    assignment_code: str
    assignment_title: str = ""
    evaluation_date: str = ""
    max_score: float = 0.0
    coursework_id: Optional[str] = None


class ScoreMatrixStudent(BaseModel):
    """Row in the Score Matrix view."""

    student_id: str
    student_name: str
    display_name: str = ""
    courses: list[CourseEnrolment] = Field(default_factory=list)


class ScoreCell(BaseModel):
    earned: float
    max: float
    percentage: float


class ScoreMatrixCourse(BaseModel):
    course_id: str
    label: str
    section: Optional[str] = None
    enrollment_code: Optional[str] = None


class ScoreMatrixResponse(BaseModel):
    """Pivoted student × assignment matrix backing the Scores page."""

    assignments: list[ScoreMatrixAssignment]
    students: list[ScoreMatrixStudent]
    cells: dict[str, dict[str, ScoreCell]]
    courses: list[ScoreMatrixCourse] = Field(default_factory=list)


# ───────── Reports / wire / stats / budget ─────────

class ReportRow(BaseModel):
    student_id: str
    student_name: str
    assignment_type: Tier
    assignment_code: str
    assignment_title: str
    coursework_id: Optional[str] = None
    percentage: float
    band: Band
    evaluation_date: str
    report_drive_id: str
    report_url: str
    linked_at: Optional[str] = None
    unlinked_at: Optional[str] = None
    shared_with_email: Optional[str] = None
    drive_permission_id: Optional[str] = None
    eval_duration_seconds: Optional[int] = None


class WireItem(BaseModel):
    """A row in the Wire view — recent graded results across all courses."""

    student_id: str
    student_name: str
    assignment_type: Tier
    assignment_code: str
    assignment_title: str
    percentage: float
    band: Band
    qualifies_for: Optional[str] = None
    report_url: Optional[str] = None
    report_drive_id: Optional[str] = None


class DistributionResponse(BaseModel):
    trailblazer: int
    qualifier: int
    developing: int
    foundational_gaps: int
    total: int
    week_label: str


class StatsResponse(BaseModel):
    awaiting_keys: int
    submissions_queued: int
    estimated_cost_usd: float
    week_distribution: DistributionResponse


class BudgetResponse(BaseModel):
    budget_usd: float
    spent_usd: float
    available_usd: float
    cost_per_grading_usd: float


# ───────── Rubric / thresholds / tier cutoffs ─────────

class RubricDimension(BaseModel):
    key: str
    name: str
    weight: float
    description: str


class Thresholds(BaseModel):
    trailblazer: int = Field(default=75, ge=0, le=100)
    qualifier: int = Field(default=60, ge=0, le=100)
    developing: int = Field(default=45, ge=0, le=100)

    @field_validator("qualifier")
    @classmethod
    def _qualifier_below_trailblazer(cls, v: int, info) -> int:
        tb = info.data.get("trailblazer")
        if tb is not None and v >= tb:
            raise ValueError("qualifier must be < trailblazer")
        return v

    @field_validator("developing")
    @classmethod
    def _developing_below_qualifier(cls, v: int, info) -> int:
        q = info.data.get("qualifier")
        if q is not None and v >= q:
            raise ValueError("developing must be < qualifier")
        return v


class TierCutoffs(BaseModel):
    """Per-tier pass cutoffs. None = terminal tier (no pass concept).
    WA/QA/ZA are editable; AA stays terminal and is read-only in the UI.
    """

    WA: Optional[int] = Field(default=None, ge=0, le=100)
    QA: Optional[int] = Field(default=None, ge=0, le=100)
    AA: Optional[int] = Field(default=None, ge=0, le=100)
    ZA: Optional[int] = Field(default=None, ge=0, le=100)


class RubricResponse(BaseModel):
    dimensions: list[RubricDimension]
    per_question_scores: list[float]
    bands: Thresholds
    band_labels: dict[str, str]
