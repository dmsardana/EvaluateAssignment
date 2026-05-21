/**
 * Typed client for FastAPI endpoints. All paths are relative — Next.js
 * rewrites /api/* to http://localhost:8000/api/* in development.
 */

export type AssignmentType = "WA" | "QA" | "AA" | "ZA";

export type QueueStatus =
  | "DETECTED"
  | "GENERATING"
  | "PENDING_REVIEW"
  | "NEEDS_REGEN"
  | "APPROVED"
  | "SHARED";

export type Band = "TRBLZ" | "QUALIF" | "DEVLP" | "F-GAPS";

export interface QueueItem {
  coursework_id: string;
  course_id: string;
  assignment_type: AssignmentType;
  assignment_code: string;
  assignment_title: string;
  status: QueueStatus;
  submission_count: number;
  questions_count: number;
  flagged_count: number;
  current_otp: string | null;
  model: string | null;
  generated_at: string | null;
  approved_at?: string | null;
  detected_at?: string | null;
  ak_drive_id?: string | null;
}

export type QuestionStatus = "pending" | "approved" | "needs_rework";

export interface Question {
  number: number | string;
  question_text: string;
  difficulty: string | null;
  approach: string | null;
  solution: string | null;
  final_answer: string | null;
  concise: string | null;
  common_mistakes: string | null;
}

export interface SubmissionAttachment {
  title: string;
  url: string | null;
  drive_id: string | null;
}

export interface Submission {
  student_id: string;
  student_name: string;
  submission_id: string | null;
  state: string;
  submitted_at: string;
  late: boolean;
  attachments: SubmissionAttachment[];
  alternate_link: string | null;
  graded_percentage: number | null;
  graded_earned: number | null;
  graded_max: number | null;
  // Populated after a successful evaluation. The queue-detail endpoint
  // joins the scores table into the Classroom submissions before
  // returning, so these reflect the latest graded run.
  graded_at?: string | null;
  report_drive_id?: string | null;
  report_url?: string | null;
  linked_at?: string | null;
  unlinked_at?: string | null;
}

export interface Material {
  kind: "drive_file" | "link" | "youtube" | "form";
  title: string;
  url: string | null;
  drive_id: string | null;
  thumbnail_url: string | null;
}

export interface GenerationProgress {
  stage: string;
  label: string;
  percent: number;
  started_at: string;
  updated_at: string;
}

export interface QueueDetail extends QueueItem {
  created_at: string | null;
  due_at: string | null;
  alternate_link: string | null;
  questions: Question[];
  questions_status: QuestionStatus[];
  drive_pdf_id: string | null;
  regen_count: number;
  description: string;
  materials: Material[];
  submissions: Submission[];
  work_type: string | null;
  max_points: number | null;
  generation_progress: GenerationProgress | null;
  errors: Array<Record<string, unknown>>;
  raw_submission_count: number | null;
}

export interface StudentProfilePatch {
  student_name?: string | null;
  display_name?: string | null;
  email?: string | null;
  mobile?: string | null;
}

export interface ReprocessRequestBody {
  flagged_question_numbers: number[];
}

export interface EvaluateRequestBody {
  student_ids?: string[];
  concurrency?: number;
  force_reeval?: boolean;
  model?: string;
  // Phase 2 LLM routing — one of "anthropic" | "gemini" | "openai".
  // Optional; backend defaults to "anthropic".
  provider?: string;
}

export interface BudgetResponse {
  // /api/budget returns an open-ended object; treat as a record of strings to unknown.
  [k: string]: unknown;
}

export interface EvaluationProgressEntry {
  status?: string;
  percent?: number;
  started_at?: string;
  updated_at?: string;
  finished_at?: string | null;
  elapsed_seconds?: number;
  message?: string;
  [k: string]: unknown;
}

export interface EvaluationProgressResponse {
  progress: Record<string, EvaluationProgressEntry>;
}

export interface BulkProgressResponse {
  // server returns an open-ended dict; values vary. Treat permissively.
  [k: string]: unknown;
}

export interface ReportRow {
  student_id: string;
  student_name: string;
  assignment_type: AssignmentType;
  assignment_code: string;
  assignment_title: string;
  coursework_id: string | null;
  percentage: number;
  band: Band;
  evaluation_date: string;
  report_drive_id: string;
  report_url: string;
  linked_at: string | null;
  unlinked_at: string | null;
}

export interface CourseEnrolment {
  course_id: string;
  name: string;
  section: string | null;
  enrollment_code: string | null;
  label: string;
}

export interface StudentProfile {
  student_id: string;
  student_name: string;
  display_name: string | null;
  email: string | null;
  mobile: string | null;
  updated_at: string | null;
  in_roster: boolean;
  courses: CourseEnrolment[];
}

export interface ScoreCell {
  earned: number;
  max: number;
  percentage: number;
}

export interface ScoreMatrixAssignment {
  key: string;
  assignment_type: AssignmentType;
  assignment_code: string;
  assignment_title: string;
  evaluation_date: string;
  max_score: number;
  coursework_id: string | null;
}

export interface ScoreMatrixStudent {
  student_id: string;
  student_name: string;
  display_name: string;
  courses: CourseEnrolment[];
}

export interface ScoreMatrixCourse {
  course_id: string;
  label: string;
  section: string | null;
  enrollment_code: string | null;
}

export interface ScoreMatrixResponse {
  assignments: ScoreMatrixAssignment[];
  students: ScoreMatrixStudent[];
  cells: Record<string, Record<string, ScoreCell>>;
  courses?: ScoreMatrixCourse[];
}

export interface DistributionResponse {
  trailblazer: number;
  qualifier: number;
  developing: number;
  foundational_gaps: number;
  total: number;
  week_label: string;
}

export interface StatsResponse {
  awaiting_keys: number;
  submissions_queued: number;
  estimated_cost_usd: number;
  week_distribution: DistributionResponse;
}

export interface RubricDimension {
  key: string;
  name: string;
  weight: number;
  description: string;
}

export interface Thresholds {
  trailblazer: number;
  qualifier: number;
  developing: number;
}

export interface TierCutoffs {
  WA: number | null;
  QA: number | null;
  AA: number | null;
  ZA: number | null;
}

export interface RubricResponse {
  dimensions: RubricDimension[];
  per_question_scores: number[];
  bands: Thresholds;
  band_labels: Record<string, string>;
}

async function jget<T>(path: string): Promise<T> {
  const r = await fetch(path, { credentials: "include" });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} — ${path}`);
  return r.json() as Promise<T>;
}

async function jpost<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(path, {
    method: "POST",
    credentials: "include",
    headers: body ? { "content-type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) {
    const detail = await r.json().catch(() => ({}));
    throw new Error(detail.detail || `${r.status} ${r.statusText}`);
  }
  return (await r.json().catch(() => ({}))) as T;
}

async function jput<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(path, {
    method: "PUT",
    credentials: "include",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const detail = await r.json().catch(() => ({}));
    throw new Error(detail.detail || `${r.status} ${r.statusText}`);
  }
  return (await r.json().catch(() => ({}))) as T;
}

export const api = {
  queue: () => jget<QueueItem[]>("/api/queue"),
  queueItem: (id: string) => jget<QueueDetail>(`/api/queue/${id}`),
  approve: (id: string) => jpost<unknown>(`/api/queue/${id}/approve`),
  abort: (id: string) => jpost<unknown>(`/api/queue/${id}/abort`),
  generate: (id: string) => jpost<unknown>(`/api/queue/${id}/generate`),
  reprocess: (id: string, body?: ReprocessRequestBody) =>
    jpost<unknown>(`/api/queue/${id}/reprocess`, body),
  evaluate: (id: string, body?: EvaluateRequestBody) =>
    jpost<unknown>(`/api/queue/${id}/evaluate`, body),
  evaluationsAbort: (id: string) =>
    jpost<unknown>(`/api/queue/${id}/evaluations/abort`),
  evaluationsProgress: (id: string) =>
    jget<EvaluationProgressResponse>(`/api/queue/${id}/evaluations/progress`),
  bulkProgress: (id: string) =>
    jget<BulkProgressResponse>(`/api/queue/${id}/bulk-progress`),
  shareSubmission: (id: string, studentId: string) =>
    jpost<unknown>(`/api/queue/${id}/submissions/${studentId}/share`),
  unshareSubmission: (id: string, studentId: string) =>
    jpost<unknown>(`/api/queue/${id}/submissions/${studentId}/unshare`),
  setQuestionStatus: (id: string, n: number, status: QuestionStatus) =>
    jpost<unknown>(`/api/queue/${id}/questions/${n}/status`, { status }),
  linkAll: (id: string) =>
    jpost<unknown>(`/api/queue/${id}/link-all-graded`),
  unlinkAll: (id: string) =>
    jpost<unknown>(`/api/queue/${id}/unlink-all-linked`),
  linkSubmission: (id: string, studentId: string) =>
    jpost<unknown>(`/api/queue/${id}/submissions/${studentId}/link`),
  unlinkSubmission: (id: string, studentId: string) =>
    jpost<unknown>(`/api/queue/${id}/submissions/${studentId}/unlink`),
  reports: () => jget<ReportRow[]>("/api/reports"),
  students: () => jget<StudentProfile[]>("/api/students"),
  setStudent: (id: string, patch: StudentProfilePatch) =>
    jput<StudentProfile>(`/api/students/${id}`, patch),
  scoresMatrix: () => jget<ScoreMatrixResponse>("/api/scores-matrix"),
  stats: () => jget<StatsResponse>("/api/stats"),
  budget: () => jget<BudgetResponse>("/api/budget"),
  distribution: () => jget<DistributionResponse>("/api/distribution"),
  rubric: () => jget<RubricResponse>("/api/settings/rubric"),
  thresholds: () => jget<Thresholds>("/api/settings/thresholds"),
  setThresholds: (body: Thresholds) =>
    jput<Thresholds>("/api/settings/thresholds", body),
  tierCutoffs: () => jget<TierCutoffs>("/api/settings/tier-cutoffs"),
  setTierCutoffs: (body: TierCutoffs) =>
    jput<TierCutoffs>("/api/settings/tier-cutoffs", body),
};
