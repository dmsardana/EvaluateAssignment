"use client";

import Link from "next/link";
import { use, useEffect, useMemo, useState } from "react";
import useSWR from "swr";

import { CollapsibleSection } from "@/components/collapsible-section";
import { MathText } from "@/components/math";
import {
  ModelPicker,
  selectionFromStored,
} from "@/components/model-picker";
import {
  ErrorState,
  LoadingState,
  StatusPill,
  TypePill,
} from "@/components/page-chrome";
import {
  api,
  EvaluationProgressEntry,
  EvaluationProgressResponse,
  Question,
  QueueDetail,
  QuestionStatus,
  Submission,
} from "@/lib/api";

const Q_STATUS_TONE: Record<QuestionStatus, string> = {
  pending: "border-ink-10 bg-ink-5 text-ink-40",
  approved:
    "border-[rgba(190,242,100,0.4)] bg-[rgba(190,242,100,0.1)] text-[var(--lime)]",
  needs_rework:
    "border-[rgba(248,113,113,0.4)] bg-[rgba(248,113,113,0.1)] text-[var(--ts-red)]",
};

export default function QueueDrawerPage({
  params,
}: {
  params: Promise<{ coursework_id: string }>;
}) {
  const { coursework_id: id } = use(params);
  const detailSWR = useSWR<QueueDetail>(
    `/api/queue/${id}`,
    () => api.queueItem(id),
    { refreshInterval: 8_000 },
  );

  const progressSWR = useSWR<EvaluationProgressResponse>(
    `/api/queue/${id}/evaluations/progress`,
    () => api.evaluationsProgress(id),
    {
      refreshInterval: (latest) => {
        if (!latest) return 5_000;
        // Terminal statuses written by services/queue.py:_eval_record —
        // anything else means a worker is still mid-flight. "failed"
        // must be here: the backend writes it (not "error") on
        // calling_claude / no-submission / generate_report failures, and
        // before this fix the clock spun forever on those rows.
        const TERMINAL = new Set(["done", "error", "failed", "cancelled"]);
        const inFlight = Object.values(latest.progress).some(
          (p) => p.status && !TERMINAL.has(p.status),
        );
        return inFlight ? 2_500 : 15_000;
      },
    },
  );

  return (
    <div>
      <BackBar />
      {detailSWR.isLoading && <LoadingState label="loading assignment" />}
      {detailSWR.error && <ErrorState error={detailSWR.error} />}
      {detailSWR.data && (
        <Body
          detail={detailSWR.data}
          progress={progressSWR.data?.progress ?? {}}
          onDetailMutate={detailSWR.mutate}
          onProgressMutate={progressSWR.mutate}
        />
      )}
    </div>
  );
}

function BackBar() {
  return (
    <div className="border-b border-ink-10 px-6 py-4 md:px-10">
      <Link
        href="/"
        className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-ink-40 hover:text-ink-100"
      >
        ← Approval queue
      </Link>
    </div>
  );
}

function Body({
  detail,
  progress,
  onDetailMutate,
  onProgressMutate,
}: {
  detail: QueueDetail;
  progress: Record<string, EvaluationProgressEntry>;
  onDetailMutate: () => Promise<unknown> | void;
  onProgressMutate: () => Promise<unknown> | void;
}) {
  const flaggedNumbers = detail.questions
    .map((q, i) =>
      detail.questions_status[i] === "needs_rework"
        ? Number(q.number)
        : null,
    )
    .filter((n): n is number => Number.isFinite(n as number));

  async function refreshAll() {
    await Promise.all([onDetailMutate(), onProgressMutate()]);
  }

  return (
    <>
      <Hero detail={detail} onMutate={refreshAll} />

      {detail.generation_progress && (
        <section className="px-6 pb-8 md:px-10">
          <GenerationProgressCard progress={detail.generation_progress} />
        </section>
      )}

      {detail.errors.length > 0 && (
        <section className="px-6 pb-8 md:px-10">
          <ErrorsCard errors={detail.errors} />
        </section>
      )}

      <CollapsibleSection
        courseworkId={detail.coursework_id}
        name="submissions"
        title="Submissions"
        sub={`${detail.submissions.length} student${detail.submissions.length === 1 ? "" : "s"}`}
        defaultOpen={true}
      >
        <SubmissionsBody
          detail={detail}
          progress={progress}
          onMutate={refreshAll}
        />
      </CollapsibleSection>

      <CollapsibleSection
        courseworkId={detail.coursework_id}
        name="questions"
        title="Questions"
        sub={`${detail.questions.length} · cycle status to flag`}
        defaultOpen={true}
        toolbar={
          flaggedNumbers.length > 0 ? (
            <ReprocessFlaggedButton
              detail={detail}
              flaggedNumbers={flaggedNumbers}
              onMutate={refreshAll}
            />
          ) : null
        }
      >
        <div className="space-y-4">
          {detail.questions.map((q, i) => (
            <QuestionPanel
              key={`${q.number}-${i}`}
              question={q}
              status={detail.questions_status[i] ?? "pending"}
              courseworkId={detail.coursework_id}
              onChanged={refreshAll}
            />
          ))}
        </div>
      </CollapsibleSection>

      <CollapsibleSection
        courseworkId={detail.coursework_id}
        name="meta"
        title="Metadata"
        sub="reference"
        defaultOpen={false}
      >
        <MetaGrid detail={detail} />
      </CollapsibleSection>
    </>
  );
}

function Hero({
  detail,
  onMutate,
}: {
  detail: QueueDetail;
  onMutate: () => Promise<unknown> | void;
}) {
  return (
    <section className="px-6 py-10 md:px-10">
      <div className="flex flex-wrap items-center gap-2">
        <TypePill type={detail.assignment_type} />
        <span className="font-mono text-[11px] text-ink-40">
          {detail.assignment_code}
        </span>
        <StatusPill status={detail.status} />
        {detail.current_otp && (
          <span className="rounded border border-ink-10 bg-ink-5 px-2 py-[3px] font-mono text-[10.5px] text-ink-80">
            OTP {detail.current_otp}
          </span>
        )}
        {detail.regen_count > 0 && (
          <span className="rounded border border-ink-10 bg-ink-5 px-2 py-[3px] font-mono text-[10.5px] text-ink-40">
            regen ×{detail.regen_count}
          </span>
        )}
        {detail.model && (
          <span className="rounded border border-ink-10 bg-ink-5 px-2 py-[3px] font-mono text-[10.5px] text-ink-40">
            AK model · {detail.model}
          </span>
        )}
      </div>
      <h1 className="mt-4 font-display text-[40px] font-semibold leading-[1.04] tracking-[-0.015em] text-ink-100 md:text-[52px]">
        {detail.assignment_title || detail.assignment_code}
      </h1>
      {detail.description && (
        <p className="mt-3 max-w-3xl text-[14px] leading-relaxed text-ink-80">
          {detail.description}
        </p>
      )}
      <HeroToolbar detail={detail} onMutate={onMutate} />
    </section>
  );
}

function HeroToolbar({
  detail,
  onMutate,
}: {
  detail: QueueDetail;
  onMutate: () => Promise<unknown> | void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function run(name: string, fn: () => Promise<unknown>) {
    setBusy(name);
    setErr(null);
    try {
      await fn();
      await onMutate();
    } catch (e: unknown) {
      setErr((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mt-6 flex flex-wrap items-center gap-2">
      {detail.status === "PENDING_REVIEW" && (
        <TBtn
          tone="lime"
          label="Approve"
          busy={busy === "approve"}
          onClick={() => run("approve", () => api.approve(detail.coursework_id))}
        />
      )}
      {detail.status === "DETECTED" && (
        <TBtn
          label="Generate AK"
          busy={busy === "gen"}
          onClick={() => run("gen", () => api.generate(detail.coursework_id))}
        />
      )}
      {detail.status !== "APPROVED" && detail.status !== "SHARED" && (
        <TBtn
          tone="ghost"
          label="Abort"
          busy={busy === "abort"}
          onClick={() => run("abort", () => api.abort(detail.coursework_id))}
        />
      )}
      {detail.drive_pdf_id && (
        <a
          href={`https://drive.google.com/file/d/${detail.drive_pdf_id}/view`}
          target="_blank"
          rel="noreferrer"
          className="rounded-md border border-ink-10 bg-ink-5 px-3 py-[6px] font-sans text-[12px] text-ink-100 hover:border-[rgba(34,211,238,0.4)]"
        >
          AK PDF ↗
        </a>
      )}
      {detail.alternate_link && (
        <a
          href={detail.alternate_link}
          target="_blank"
          rel="noreferrer"
          className="rounded-md border border-ink-10 bg-ink-5 px-3 py-[6px] font-sans text-[12px] text-ink-100 hover:border-[rgba(34,211,238,0.4)]"
        >
          Classroom ↗
        </a>
      )}
      {err && (
        <span className="font-mono text-[11px] text-[var(--ts-red)]">{err}</span>
      )}
    </div>
  );
}

function ReprocessFlaggedButton({
  detail,
  flaggedNumbers,
  onMutate,
}: {
  detail: QueueDetail;
  flaggedNumbers: number[];
  onMutate: () => Promise<unknown> | void;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function fire() {
    setBusy(true);
    setErr(null);
    try {
      await api.reprocess(detail.coursework_id, {
        flagged_question_numbers: flaggedNumbers,
      });
      await onMutate();
    } catch (e: unknown) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center gap-2">
      {err && (
        <span className="font-mono text-[11px] text-[var(--ts-red)]">{err}</span>
      )}
      <TBtn
        label={`Reprocess ${flaggedNumbers.length} flagged`}
        busy={busy}
        onClick={fire}
      />
    </div>
  );
}

function GenerationProgressCard({
  progress,
}: {
  progress: NonNullable<QueueDetail["generation_progress"]>;
}) {
  return (
    <div className="rounded-xl border border-[rgba(34,211,238,0.4)] bg-[rgba(34,211,238,0.05)] p-5">
      <div className="flex items-baseline justify-between">
        <h3 className="font-display text-[18px] text-ink-100">
          {progress.label}
        </h3>
        <span className="font-mono text-[11px] tabular-nums text-[var(--cyan)]">
          {progress.percent}%
        </span>
      </div>
      <div className="mt-3 h-[3px] w-full overflow-hidden rounded-full bg-ink-10">
        <div
          className="h-full rounded-full"
          style={{
            width: `${progress.percent}%`,
            background: "linear-gradient(90deg, var(--cyan), var(--violet))",
            boxShadow: "0 0 12px var(--cyan)",
          }}
        />
      </div>
      <div className="mt-2 font-mono text-[10.5px] text-ink-40">
        stage · {progress.stage} · updated{" "}
        {new Date(progress.updated_at).toLocaleTimeString()}
      </div>
    </div>
  );
}

function ErrorsCard({ errors }: { errors: Array<Record<string, unknown>> }) {
  return (
    <div className="rounded-xl border border-[rgba(248,113,113,0.4)] bg-[rgba(248,113,113,0.06)] p-5">
      <h3 className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-[var(--ts-red)]">
        {errors.length} error{errors.length === 1 ? "" : "s"}
      </h3>
      <ul className="mt-2 space-y-1 font-mono text-[11px] text-ink-80">
        {errors.slice(0, 5).map((e, i) => (
          <li key={i} className="line-clamp-2">
            {JSON.stringify(e)}
          </li>
        ))}
      </ul>
    </div>
  );
}

// ───────── Submissions ─────────

function SubmissionsBody({
  detail,
  progress,
  onMutate,
}: {
  detail: QueueDetail;
  progress: Record<string, EvaluationProgressEntry>;
  onMutate: () => Promise<unknown> | void;
}) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const subs = useMemo(
    () =>
      [...detail.submissions].sort((a, b) =>
        a.student_name.localeCompare(b.student_name),
      ),
    [detail.submissions],
  );

  useEffect(() => {
    setSelected((prev) => {
      const live = new Set(subs.map((s) => s.student_id));
      const next = new Set<string>();
      for (const id of prev) if (live.has(id)) next.add(id);
      return next.size === prev.size ? prev : next;
    });
  }, [subs]);

  function toggleOne(studentId: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(studentId)) next.delete(studentId);
      else next.add(studentId);
      return next;
    });
  }
  function toggleAll() {
    if (selected.size === subs.length) setSelected(new Set());
    else setSelected(new Set(subs.map((s) => s.student_id)));
  }

  async function run(name: string, fn: () => Promise<unknown>) {
    setBusy(name);
    setErr(null);
    try {
      await fn();
      await onMutate();
    } catch (e: unknown) {
      setErr((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function evaluateSelected(force: boolean) {
    if (selected.size === 0) return;
    // Backend currently ignores `model` and crashes with "unexpected keyword
    // argument" — see plan file. Selection still persists for when backend
    // routes it.
    selectionFromStored(detail.coursework_id, detail.model);
    await run("evalSelected", () =>
      api.evaluate(detail.coursework_id, {
        student_ids: [...selected],
        force_reeval: force,
      }),
    );
  }

  async function evaluateAll(force: boolean) {
    selectionFromStored(detail.coursework_id, detail.model);
    await run("evalAll", () =>
      api.evaluate(detail.coursework_id, {
        student_ids: subs.map((s) => s.student_id),
        force_reeval: force,
      }),
    );
  }

  return (
    <>
      <div className="space-y-3">
        <ModelPicker
          courseworkId={detail.coursework_id}
          defaultModel={detail.model}
        />
        <div className="flex flex-wrap items-center gap-2 rounded-xl border border-ink-10 bg-[rgba(24,24,27,0.4)] p-3">
          <span className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-ink-40">
            {selected.size > 0
              ? `${selected.size} selected`
              : `${subs.length} total`}
          </span>
          <TBtn
            tone="lime"
            label={
              selected.size > 0 ? `Evaluate ${selected.size}` : "Evaluate all"
            }
            busy={busy === "evalSelected" || busy === "evalAll"}
            onClick={() =>
              selected.size > 0
                ? evaluateSelected(false)
                : evaluateAll(false)
            }
          />
          <TBtn
            label={
              selected.size > 0 ? "Re-eval (force)" : "Re-eval all (force)"
            }
            busy={busy === "evalSelected" || busy === "evalAll"}
            onClick={() =>
              selected.size > 0 ? evaluateSelected(true) : evaluateAll(true)
            }
          />
          <TBtn
            tone="ghost"
            label="Abort evaluations"
            busy={busy === "abortEval"}
            onClick={() =>
              run("abortEval", () => api.evaluationsAbort(detail.coursework_id))
            }
          />
          <span className="mx-2 h-5 w-px bg-ink-10" />
          <TBtn
            label="Link all graded"
            busy={busy === "linkAll"}
            onClick={() =>
              run("linkAll", () => api.linkAll(detail.coursework_id))
            }
          />
          <TBtn
            tone="ghost"
            label="Unlink all"
            busy={busy === "unlinkAll"}
            onClick={() =>
              run("unlinkAll", () => api.unlinkAll(detail.coursework_id))
            }
          />
          {err && (
            <span className="font-mono text-[11px] text-[var(--ts-red)]">
              {err}
            </span>
          )}
        </div>
      </div>

      {subs.length === 0 ? (
        <div className="mt-6 rounded-xl border border-dashed border-ink-10 bg-[rgba(24,24,27,0.45)] px-6 py-10 text-center text-ink-40">
          No submissions yet.
        </div>
      ) : (
        <div className="mt-6 overflow-x-auto rounded-xl border border-ink-10">
          <table className="w-full border-collapse text-left text-[13px]">
            <thead className="bg-[rgba(24,24,27,0.6)] text-ink-40">
              <tr>
                <Th className="w-8">
                  <input
                    type="checkbox"
                    aria-label="Select all"
                    checked={
                      selected.size > 0 && selected.size === subs.length
                    }
                    onChange={toggleAll}
                    className="accent-[var(--ts-red)]"
                  />
                </Th>
                <Th>Student</Th>
                <Th>State</Th>
                <Th>Attachments</Th>
                <Th>Progress</Th>
                <Th className="text-right">Score</Th>
                <Th />
              </tr>
            </thead>
            <tbody>
              {subs.map((s, i) => (
                <SubmissionRow
                  key={`${s.student_id}-${i}`}
                  sub={s}
                  zebra={i % 2 === 1}
                  selected={selected.has(s.student_id)}
                  onToggle={() => toggleOne(s.student_id)}
                  progressEntry={progress[s.student_id]}
                  courseworkId={detail.coursework_id}
                  defaultModel={detail.model}
                  onMutate={onMutate}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

function SubmissionRow({
  sub,
  zebra,
  selected,
  onToggle,
  progressEntry,
  courseworkId,
  defaultModel,
  onMutate,
}: {
  sub: Submission;
  zebra: boolean;
  selected: boolean;
  onToggle: () => void;
  progressEntry?: EvaluationProgressEntry;
  courseworkId: string;
  defaultModel: string | null;
  onMutate: () => Promise<unknown> | void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function run(name: string, fn: () => Promise<unknown>) {
    setBusy(name);
    setErr(null);
    try {
      await fn();
      await onMutate();
    } catch (e: unknown) {
      setErr((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function evaluateOne(force: boolean) {
    // Backend currently ignores `model`; see plan file. Touch the stored
    // selection so its key keeps tracking the operator's choice.
    selectionFromStored(courseworkId, defaultModel);
    await run("eval", () =>
      api.evaluate(courseworkId, {
        student_ids: [sub.student_id],
        force_reeval: force,
      }),
    );
  }

  const isGraded = sub.graded_percentage !== null;
  const subAny = sub as Submission & {
    report_url?: string | null;
    report_drive_id?: string | null;
  };
  const viewUrl =
    subAny.report_url ??
    (subAny.report_drive_id
      ? `https://drive.google.com/file/d/${subAny.report_drive_id}/view`
      : null);

  return (
    <tr
      className={`border-t border-ink-10 transition hover:bg-[rgba(248,113,113,0.04)] ${
        zebra ? "bg-[rgba(24,24,27,0.35)]" : ""
      }`}
    >
      <Td>
        <input
          type="checkbox"
          aria-label={`Select ${sub.student_name}`}
          checked={selected}
          onChange={onToggle}
          className="accent-[var(--ts-red)]"
        />
      </Td>
      <Td className="text-ink-100">
        <div className="font-medium">{sub.student_name}</div>
        <div className="font-mono text-[10px] text-ink-40">{sub.student_id}</div>
      </Td>
      <Td className="font-mono text-[11px] text-ink-40">
        <div>{sub.state}</div>
        <div className="mt-0.5 text-ink-40">
          {sub.submitted_at ? new Date(sub.submitted_at).toLocaleString() : "—"}
        </div>
        {sub.late && (
          <span className="mt-1 inline-block rounded border border-[rgba(236,72,153,0.4)] px-1.5 py-[1px] text-[10px] text-[var(--magenta)]">
            late
          </span>
        )}
      </Td>
      <Td>
        {sub.attachments.length === 0 ? (
          <span className="text-ink-40">—</span>
        ) : (
          <ul className="space-y-1">
            {sub.attachments.map((a, i) => (
              <li key={i}>
                {a.url ? (
                  <a
                    href={a.url}
                    target="_blank"
                    rel="noreferrer"
                    className="font-mono text-[11px] text-[var(--cyan)] hover:text-ink-100"
                  >
                    {a.title} ↗
                  </a>
                ) : (
                  <span className="font-mono text-[11px] text-ink-80">
                    {a.title}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </Td>
      <Td>
        <ProgressCell entry={progressEntry} />
      </Td>
      <Td className="text-right">
        {isGraded ? (
          <div className="flex flex-col items-end">
            <span className="font-mono text-[13px] tabular-nums text-ink-100">
              {sub.graded_percentage?.toFixed(1)}%
            </span>
            {sub.graded_earned !== null && sub.graded_max !== null && (
              <span className="font-mono text-[10px] text-ink-40">
                {sub.graded_earned.toFixed(1)}/{sub.graded_max.toFixed(0)}
              </span>
            )}
          </div>
        ) : (
          <span className="font-mono text-[11px] text-ink-40">ungraded</span>
        )}
      </Td>
      <Td className="text-right">
        <div className="flex flex-wrap items-center justify-end gap-1.5">
          <RowAction
            label={isGraded ? "Re-eval" : "Evaluate"}
            tone={isGraded ? "default" : "lime"}
            busy={busy === "eval"}
            onClick={() => evaluateOne(isGraded)}
          />
          {viewUrl && (
            <a
              href={viewUrl}
              target="_blank"
              rel="noreferrer"
              className="rounded border border-ink-10 bg-ink-5 px-2 py-[3px] font-mono text-[10.5px] uppercase tracking-[0.14em] text-ink-100 hover:border-[rgba(34,211,238,0.4)]"
            >
              View Report ↗
            </a>
          )}
          {isGraded ? (
            <button
              type="button"
              disabled={busy !== null}
              onClick={() =>
                run("unlink", () =>
                  api.unlinkSubmission(courseworkId, sub.student_id),
                )
              }
              className="font-mono text-[10.5px] uppercase tracking-[0.14em] text-ink-40 hover:text-[var(--ts-red)]"
            >
              {busy === "unlink" ? "…" : "Unlink Report"}
            </button>
          ) : (
            <button
              type="button"
              disabled={busy !== null}
              onClick={() =>
                run("link", () =>
                  api.linkSubmission(courseworkId, sub.student_id),
                )
              }
              className="font-mono text-[10.5px] uppercase tracking-[0.14em] text-ink-40 hover:text-[var(--lime)]"
            >
              {busy === "link" ? "…" : "Link Report"}
            </button>
          )}
        </div>
        {err && (
          <div className="mt-1 text-right font-mono text-[10px] text-[var(--ts-red)]">
            {err}
          </div>
        )}
      </Td>
    </tr>
  );
}

function RowAction({
  label,
  busy,
  onClick,
  tone = "default",
}: {
  label: string;
  busy: boolean;
  onClick: () => void;
  tone?: "default" | "lime" | "ghost";
}) {
  const cls =
    tone === "lime"
      ? "border-[rgba(190,242,100,0.4)] bg-[rgba(190,242,100,0.12)] text-ink-100 hover:bg-[rgba(190,242,100,0.2)]"
      : tone === "ghost"
        ? "border-transparent text-ink-40 hover:text-[var(--ts-red)] hover:border-[rgba(248,113,113,0.3)]"
        : "border-ink-10 bg-ink-5 text-ink-100 hover:border-[rgba(34,211,238,0.4)]";
  return (
    <button
      type="button"
      disabled={busy}
      onClick={onClick}
      className={`rounded border px-2 py-[3px] font-mono text-[10.5px] uppercase tracking-[0.14em] transition disabled:opacity-50 ${cls}`}
    >
      {busy ? "…" : label}
    </button>
  );
}

function ProgressCell({ entry }: { entry?: EvaluationProgressEntry }) {
  const elapsed = useElapsedSeconds(entry);
  if (!entry || !entry.status) {
    return <span className="font-mono text-[11px] text-ink-40">idle</span>;
  }
  const done = entry.status === "done";
  const error = entry.status === "error";
  const cancelled = entry.status === "cancelled";
  const pct =
    typeof entry.percent === "number"
      ? Math.max(0, Math.min(100, entry.percent))
      : null;
  const tone = error
    ? "var(--ts-red)"
    : cancelled
      ? "var(--ink-40)"
      : done
        ? "var(--lime)"
        : "var(--cyan)";
  const statusLabel = error
    ? "error"
    : cancelled
      ? "cancelled"
      : done
        ? "done"
        : entry.status;

  return (
    <div className="min-w-[120px]">
      <div className="flex items-baseline justify-between gap-2">
        <span
          className="font-mono text-[10.5px] uppercase tracking-[0.16em]"
          style={{ color: tone }}
        >
          {statusLabel}
        </span>
        <span className="font-mono text-[10.5px] tabular-nums text-ink-40">
          {elapsed !== null ? formatElapsed(elapsed) : ""}
        </span>
      </div>
      <div className="mt-1 h-[2px] w-full overflow-hidden rounded-full bg-ink-10">
        <div
          className="h-full rounded-full transition-all"
          style={{
            width: `${pct ?? (done ? 100 : 0)}%`,
            background: tone,
            boxShadow: `0 0 8px ${tone}`,
          }}
        />
      </div>
      {entry.message && (
        <div className="mt-1 line-clamp-1 font-mono text-[10px] text-ink-40">
          {entry.message}
        </div>
      )}
    </div>
  );
}

function useElapsedSeconds(entry?: EvaluationProgressEntry): number | null {
  const [now, setNow] = useState<number>(() => Date.now());

  useEffect(() => {
    // Same terminal set as the SWR poller above. "failed" matters here
    // too — without it, the 1s ticker kept running on failed rows and
    // the elapsed-time clock spun forever even though the run was over.
    const TERMINAL = new Set(["done", "error", "failed", "cancelled"]);
    if (
      !entry ||
      !entry.started_at ||
      (entry.status && TERMINAL.has(entry.status))
    ) {
      return;
    }
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [entry]);

  if (!entry) return null;
  if (typeof entry.elapsed_seconds === "number") return entry.elapsed_seconds;
  if (!entry.started_at) return null;
  const start = new Date(entry.started_at).getTime();
  if (Number.isNaN(start)) return null;
  const end = entry.finished_at ? new Date(entry.finished_at).getTime() : now;
  return Math.max(0, Math.round((end - start) / 1000));
}

function formatElapsed(sec: number): string {
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}m ${s.toString().padStart(2, "0")}s`;
}

// ───────── Questions ─────────

function QuestionPanel({
  question,
  status,
  courseworkId,
  onChanged,
}: {
  question: Question;
  status: QuestionStatus;
  courseworkId: string;
  onChanged: () => Promise<unknown> | void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [pending, setPending] = useState(false);

  async function setStatus(next: QuestionStatus) {
    setPending(true);
    try {
      await api.setQuestionStatus(courseworkId, Number(question.number), next);
      await onChanged();
    } finally {
      setPending(false);
    }
  }

  return (
    <article className="rounded-xl border border-ink-10 bg-[rgba(24,24,27,0.5)]">
      <header className="flex flex-wrap items-baseline gap-3 border-b border-ink-10 px-5 py-3">
        <span className="rounded-md border border-ink-10 bg-ink-5 px-2 py-[2px] font-mono text-[10.5px] text-ink-80">
          Q{String(question.number).padStart(2, "0")}
        </span>
        {question.difficulty && (
          <span className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-ink-40">
            {question.difficulty}
          </span>
        )}
        <div className="ml-auto inline-flex gap-1">
          {(["pending", "approved", "needs_rework"] as QuestionStatus[]).map(
            (s) => (
              <button
                key={s}
                type="button"
                disabled={pending || s === status}
                onClick={() => setStatus(s)}
                className={`rounded border px-2 py-[3px] font-mono text-[10px] uppercase tracking-[0.14em] transition disabled:opacity-100 ${
                  s === status
                    ? Q_STATUS_TONE[s]
                    : "border-ink-10 text-ink-40 hover:text-ink-100"
                }`}
              >
                {s.replace("_", " ")}
              </button>
            ),
          )}
        </div>
      </header>
      <div className="px-5 py-4 text-[14px] leading-relaxed text-ink-100">
        <MathText>{question.question_text}</MathText>
      </div>
      {(question.approach ||
        question.solution ||
        question.final_answer ||
        question.common_mistakes ||
        question.concise) && (
        <details
          className="border-t border-ink-10"
          open={expanded}
          onToggle={(e) => setExpanded((e.target as HTMLDetailsElement).open)}
        >
          <summary className="cursor-pointer select-none px-5 py-3 font-mono text-[10.5px] uppercase tracking-[0.2em] text-ink-40 hover:text-ink-100">
            {expanded ? "Hide solution" : "Reveal solution"}
          </summary>
          <div className="space-y-4 border-t border-ink-10 px-5 py-4 text-[13px] text-ink-80">
            {question.approach && (
              <SolutionBlock label="Approach" body={question.approach} />
            )}
            {question.solution && (
              <SolutionBlock label="Solution" body={question.solution} />
            )}
            {question.final_answer && (
              <SolutionBlock
                label="Final answer"
                body={question.final_answer}
                accent="lime"
              />
            )}
            {question.concise && (
              <SolutionBlock label="Concise" body={question.concise} />
            )}
            {question.common_mistakes && (
              <SolutionBlock
                label="Common mistakes"
                body={question.common_mistakes}
                accent="ts-red"
              />
            )}
          </div>
        </details>
      )}
    </article>
  );
}

function SolutionBlock({
  label,
  body,
  accent,
}: {
  label: string;
  body: string;
  accent?: "lime" | "ts-red";
}) {
  const labelColor =
    accent === "lime"
      ? "text-[var(--lime)]"
      : accent === "ts-red"
        ? "text-[var(--ts-red)]"
        : "text-ink-40";
  return (
    <div>
      <div
        className={`font-mono text-[10px] uppercase tracking-[0.2em] ${labelColor}`}
      >
        {label}
      </div>
      <div className="mt-1">
        <MathText>{body}</MathText>
      </div>
    </div>
  );
}

// ───────── Metadata ─────────

function MetaGrid({ detail }: { detail: QueueDetail }) {
  const rows: Array<[string, string | null]> = [
    ["coursework", detail.coursework_id],
    ["course", detail.course_id],
    [
      "created",
      detail.created_at ? new Date(detail.created_at).toLocaleString() : null,
    ],
    ["due", detail.due_at ? new Date(detail.due_at).toLocaleString() : null],
    [
      "generated",
      detail.generated_at
        ? new Date(detail.generated_at).toLocaleString()
        : null,
    ],
    [
      "approved",
      detail.approved_at
        ? new Date(detail.approved_at).toLocaleString()
        : null,
    ],
    ["work type", detail.work_type],
    ["max points", detail.max_points?.toString() ?? null],
    [
      "submissions",
      `${detail.submission_count}${
        detail.raw_submission_count
          ? ` of ${detail.raw_submission_count} raw`
          : ""
      }`,
    ],
    [
      "questions",
      `${detail.questions_count} · ${detail.flagged_count} flagged`,
    ],
  ];

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <div className="rounded-xl border border-ink-10 bg-[rgba(24,24,27,0.55)] p-5">
        <h3 className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-ink-40">
          Identifiers + timing
        </h3>
        <dl className="mt-3 space-y-2 text-[12px]">
          {rows.map(([k, v]) => (
            <div key={k} className="flex items-baseline justify-between gap-3">
              <dt className="font-mono uppercase tracking-[0.16em] text-ink-40">
                {k}
              </dt>
              <dd className="text-right text-ink-80">
                {v ?? <span className="text-ink-40">—</span>}
              </dd>
            </div>
          ))}
        </dl>
      </div>
      {detail.materials.length > 0 && (
        <div className="rounded-xl border border-ink-10 bg-[rgba(24,24,27,0.55)] p-5">
          <h3 className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-ink-40">
            Materials
          </h3>
          <ul className="mt-3 space-y-2 text-[12px]">
            {detail.materials.map((m, i) => (
              <li key={i}>
                {m.url ? (
                  <a
                    href={m.url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-[var(--cyan)] hover:text-ink-100"
                  >
                    {m.title}
                  </a>
                ) : (
                  <span className="text-ink-80">{m.title}</span>
                )}
                <span className="ml-2 font-mono text-[10px] text-ink-40">
                  {m.kind}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// ───────── Shared ─────────

function TBtn({
  label,
  busy,
  onClick,
  tone = "default",
}: {
  label: string;
  busy: boolean;
  onClick: () => void;
  tone?: "default" | "lime" | "ghost";
}) {
  const cls =
    tone === "lime"
      ? "border-[rgba(190,242,100,0.4)] bg-[rgba(190,242,100,0.12)] text-ink-100 hover:bg-[rgba(190,242,100,0.2)]"
      : tone === "ghost"
        ? "border-transparent bg-transparent text-ink-40 hover:text-[var(--ts-red)] hover:border-[rgba(248,113,113,0.3)]"
        : "border-ink-10 bg-ink-5 text-ink-100 hover:border-[rgba(34,211,238,0.4)] hover:bg-[rgba(34,211,238,0.08)]";
  return (
    <button
      type="button"
      disabled={busy}
      onClick={onClick}
      className={`rounded-md border px-3 py-[6px] font-sans text-[12px] font-medium transition disabled:opacity-50 ${cls}`}
    >
      {busy ? "…" : label}
    </button>
  );
}

function Th({
  children,
  className = "",
}: {
  children?: React.ReactNode;
  className?: string;
}) {
  return (
    <th
      className={`px-4 py-3 font-mono text-[10px] font-medium uppercase tracking-[0.18em] ${className}`}
    >
      {children}
    </th>
  );
}

function Td({
  children,
  className = "",
}: {
  children?: React.ReactNode;
  className?: string;
}) {
  return <td className={`px-4 py-3 ${className}`}>{children}</td>;
}
