"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import useSWR from "swr";

import { FilterBar, FilterSummary } from "@/components/filter-bar";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  StatusPill,
  TypePill,
} from "@/components/page-chrome";
import { api, QueueItem, StudentProfile } from "@/lib/api";
import {
  ayRange,
  ayStartYear,
  defaultAyOptions,
  parseDate,
  unionAyOptions,
} from "@/lib/ay";

// Items requiring operator attention float to the top.
const ACTIONABLE: ReadonlyArray<QueueItem["status"]> = [
  "PENDING_REVIEW",
  "NEEDS_REGEN",
];

function sortQueue(items: QueueItem[]): QueueItem[] {
  return [...items].sort((a, b) => {
    const aActionable = ACTIONABLE.includes(a.status) ? 0 : 1;
    const bActionable = ACTIONABLE.includes(b.status) ? 0 : 1;
    if (aActionable !== bActionable) return aActionable - bActionable;
    return (b.generated_at ?? "").localeCompare(a.generated_at ?? "");
  });
}

function QueueCard({
  item,
  onAction,
}: {
  item: QueueItem;
  onAction: () => Promise<void> | void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const actionable = ACTIONABLE.includes(item.status);

  async function run(name: string, fn: () => Promise<unknown>) {
    setBusy(name);
    setErr(null);
    try {
      await fn();
      await onAction();
    } catch (e: unknown) {
      setErr((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <article
      className={`group relative overflow-hidden rounded-xl border bg-[rgba(24,24,27,0.55)] px-5 py-4 transition hover:border-[rgba(34,211,238,0.35)] ${
        actionable
          ? "border-[rgba(236,72,153,0.35)] shadow-[0_0_24px_rgba(236,72,153,0.08)]"
          : "border-ink-10"
      }`}
    >
      {/* Card-wide overlay link — makes the whole ribbon clickable while
          letting action buttons keep their own click handlers (they opt
          back in via pointer-events-auto below). */}
      <Link
        href={`/queue/${item.coursework_id}`}
        aria-label={`Open ${item.assignment_title || item.assignment_code}`}
        className="absolute inset-0 z-0 rounded-xl focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[var(--cyan)]"
      />
      {actionable && (
        <span
          aria-hidden
          className="absolute left-0 top-0 z-0 h-full w-[2px]"
          style={{ background: "var(--magenta)" }}
        />
      )}
      <div className="pointer-events-none relative z-10 flex flex-wrap items-start gap-x-4 gap-y-2">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <TypePill type={item.assignment_type} />
            <span className="font-mono text-[11px] text-ink-40">
              {item.assignment_code}
            </span>
            <StatusPill status={item.status} />
            {item.current_otp && (
              <span className="rounded-md border border-ink-10 bg-ink-5 px-2 py-[3px] font-mono text-[10px] text-ink-80">
                OTP {item.current_otp}
              </span>
            )}
          </div>
          <h3 className="mt-2 font-display text-[18px] leading-snug">
            <span className="text-ink-100 underline-offset-4 group-hover:underline group-hover:decoration-[var(--ts-red)]">
              {item.assignment_title || item.assignment_code}
            </span>
          </h3>
          <dl className="mt-2 flex flex-wrap gap-x-5 gap-y-1 font-mono text-[11px] text-ink-40">
            <Stat label="Submissions" value={item.submission_count} />
            <Stat label="Questions" value={item.questions_count} />
            {item.flagged_count > 0 && (
              <Stat
                label="Flagged"
                value={item.flagged_count}
                tone="text-[var(--ts-red)]"
              />
            )}
            {item.model && <Stat label="Model" value={item.model} />}
            {item.generated_at && (
              <Stat
                label="Generated"
                value={new Date(item.generated_at).toLocaleString()}
              />
            )}
          </dl>
        </div>
        <div className="pointer-events-auto flex flex-wrap items-center gap-2">
          {item.status === "DETECTED" && (
            <ActionButton
              busy={busy === "gen"}
              label="Generate"
              onClick={() => run("gen", () => api.generate(item.coursework_id))}
            />
          )}
          {item.status === "PENDING_REVIEW" && (
            <ActionButton
              busy={busy === "approve"}
              tone="lime"
              label="Approve"
              onClick={() =>
                run("approve", () => api.approve(item.coursework_id))
              }
            />
          )}
          {(item.status === "PENDING_REVIEW" ||
            item.status === "NEEDS_REGEN") && (
            <ActionButton
              busy={busy === "reprocess"}
              label="Reprocess"
              onClick={() =>
                run("reprocess", () => api.reprocess(item.coursework_id))
              }
            />
          )}
          {item.status === "APPROVED" && (
            <ActionButton
              busy={busy === "eval"}
              label="Evaluate"
              onClick={() =>
                run("eval", () => api.evaluate(item.coursework_id))
              }
            />
          )}
          {item.status !== "APPROVED" && item.status !== "SHARED" && (
            <ActionButton
              busy={busy === "abort"}
              tone="ghost"
              label="Abort"
              onClick={() => run("abort", () => api.abort(item.coursework_id))}
            />
          )}
        </div>
      </div>
      {err && (
        <div className="mt-2 font-mono text-[11px] text-[var(--ts-red)]">
          {err}
        </div>
      )}
    </article>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string | number;
  tone?: string;
}) {
  return (
    <div>
      <span className="uppercase tracking-[0.14em]">{label}</span>{" "}
      <span className={tone ?? "text-ink-80"}>{value}</span>
    </div>
  );
}

function ActionButton({
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

export default function QueuePage() {
  const { data, error, isLoading, mutate } = useSWR<QueueItem[]>(
    "/api/queue",
    () => api.queue(),
    { refreshInterval: 10_000 },
  );
  // /api/students gives us friendly course labels (with section). SWR
  // dedupes by cache key, so this shares the top-bar search's existing
  // fetch — no extra network call.
  const { data: studentsData } = useSWR<StudentProfile[]>(
    "/api/students",
    () => api.students(),
    { refreshInterval: 120_000 },
  );

  // AY + date + classroom filters. Strict date filtering: items without
  // a usable date are excluded from the range view (per spec — only show
  // assignments within the selected duration).
  const today = useMemo(() => new Date(), []);
  const currentAyStart = useMemo(() => ayStartYear(today), [today]);
  const ayOptions = useMemo(() => {
    const observed: number[] = [];
    for (const it of data ?? []) {
      const d = parseDate(it.generated_at);
      if (d) observed.push(ayStartYear(d));
    }
    return unionAyOptions(defaultAyOptions(today), observed);
  }, [data, today]);

  const courseOptions = useMemo(() => {
    // Friendly course labels come from /api/students (each StudentProfile
    // carries its courses[].label with section). Build a course_id →
    // label map and resolve labels for course_ids present in the queue.
    const labelByCourseId = new Map<string, string>();
    for (const s of studentsData ?? []) {
      for (const c of s.courses) {
        if (c.course_id && !labelByCourseId.has(c.course_id)) {
          labelByCourseId.set(c.course_id, c.label);
        }
      }
    }
    const seen = new Map<string, string>();
    for (const it of data ?? []) {
      const cid = it.course_id || "";
      if (!cid || seen.has(cid)) continue;
      // Friendly label when /api/students has it; raw course_id as last
      // resort so the option still appears (and stays filterable) even
      // before the students payload has loaded.
      seen.set(cid, labelByCourseId.get(cid) || cid);
    }
    return [...seen.entries()]
      .map(([course_id, label]) => ({ course_id, label }))
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [data, studentsData]);

  const [ay, setAy] = useState<number>(currentAyStart);
  const initial = ayRange(currentAyStart);
  const [dateFrom, setDateFrom] = useState<string>(initial.from);
  const [dateTo, setDateTo] = useState<string>(initial.to);

  // Classroom filter persists in the URL as ?course=A,B,C — survives refresh,
  // back/forward nav, and becomes a shareable deep link.
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [courseFilter, setCourseFilterState] = useState<string[]>(() => {
    const raw = searchParams?.get("course");
    return raw ? raw.split(",").filter(Boolean) : [];
  });
  const setCourseFilter = useCallback(
    (next: string[]) => {
      setCourseFilterState(next);
      const params = new URLSearchParams(searchParams?.toString() ?? "");
      if (next.length > 0) params.set("course", next.join(","));
      else params.delete("course");
      const qs = params.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [pathname, router, searchParams],
  );

  // Keep classroom filter in sync with browser back/forward navigation.
  // setCourseFilter already writes to the URL on user action; this effect
  // only handles the URL-changed-externally case (back button, deep link).
  useEffect(() => {
    const raw = searchParams?.get("course");
    const fromUrl = raw ? raw.split(",").filter(Boolean) : [];
    setCourseFilterState((current) => {
      if (
        current.length === fromUrl.length &&
        current.every((v, i) => v === fromUrl[i])
      ) {
        return current;
      }
      return fromUrl;
    });
  }, [searchParams]);

  const [tierFilter, setTierFilter] = useState<string[]>([]);

  useEffect(() => {
    const r = ayRange(ay);
    setDateFrom(r.from);
    setDateTo(r.to);
  }, [ay]);

  const filteredItems = useMemo(() => {
    if (!data) return [] as QueueItem[];
    const from = parseDate(dateFrom);
    const to = parseDate(dateTo);
    const selected = new Set(courseFilter);
    const tiers = new Set(tierFilter);
    return data.filter((i) => {
      // Date filter applies only to items that have already been
      // generated. New assignments (never processed) have no
      // generated_at and must remain visible so they can be evaluated;
      // otherwise the queue silently hides untouched coursework.
      const d = parseDate(i.generated_at);
      if (d) {
        if (from && d < from) return false;
        if (to && d > to) return false;
      }
      if (selected.size > 0 && !selected.has(i.course_id || "")) return false;
      if (tiers.size > 0 && !tiers.has(i.assignment_type)) return false;
      return true;
    });
  }, [data, dateFrom, dateTo, courseFilter, tierFilter]);

  const items = sortQueue(filteredItems);
  const actionable = items.filter((i) => ACTIONABLE.includes(i.status));
  const inFlight = items.filter((i) => i.status === "GENERATING");
  const rest = items.filter(
    (i) => !ACTIONABLE.includes(i.status) && i.status !== "GENERATING",
  );

  return (
    <div>
      <PageHeader
        eyebrow="Console · Approval Queue"
        title={
          <>
            What needs <span className="italic text-[var(--ts-red)]">you</span>.
          </>
        }
        lede="Answer keys awaiting your review or flagged for regeneration sit at the top. Everything else trails after."
        actions={
          <span className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-ink-40">
            {actionable.length > 0
              ? `${actionable.length} actionable · refreshes 10s`
              : "queue idle · refreshes 10s"}
          </span>
        }
      />

      <section className="px-6 pb-4 md:px-10">
        <FilterBar
          ay={{ value: ay, options: ayOptions, onChange: setAy }}
          dateFrom={{ value: dateFrom, onChange: setDateFrom }}
          dateTo={{ value: dateTo, onChange: setDateTo }}
          course={{
            value: courseFilter,
            options: courseOptions,
            onChange: setCourseFilter,
          }}
          tier={{
            value: tierFilter,
            onChange: setTierFilter,
          }}
        />
        <FilterSummary
          items={{ count: items.length, label: "assignments" }}
          dateFrom={dateFrom}
          dateTo={dateTo}
        />
      </section>

      {isLoading && <LoadingState label="loading queue" />}
      {error && <ErrorState error={error} />}
      {!isLoading && !error && items.length === 0 && (
        <EmptyState
          title="No assignments in this range."
          hint="Widen the date range or change the academic year, or wait for new coursework in Google Classroom."
        />
      )}

      {actionable.length > 0 && (
        <Section title="Awaiting you" count={actionable.length}>
          {actionable.map((it) => (
            <QueueCard key={it.coursework_id} item={it} onAction={mutate} />
          ))}
        </Section>
      )}

      {inFlight.length > 0 && (
        <Section title="In flight" count={inFlight.length}>
          {inFlight.map((it) => (
            <QueueCard key={it.coursework_id} item={it} onAction={mutate} />
          ))}
        </Section>
      )}

      {rest.length > 0 && (
        <Section title="Rest of queue" count={rest.length}>
          {rest.map((it) => (
            <QueueCard key={it.coursework_id} item={it} onAction={mutate} />
          ))}
        </Section>
      )}
    </div>
  );
}

function Section({
  title,
  count,
  children,
}: {
  title: string;
  count: number;
  children: React.ReactNode;
}) {
  return (
    <section className="px-6 pb-8 pt-10 md:px-10">
      <div className="mb-4 flex items-baseline justify-between">
        <h2 className="font-display text-[22px] text-ink-100">{title}</h2>
        <span className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-ink-40">
          {count} item{count === 1 ? "" : "s"}
        </span>
      </div>
      <div className="space-y-3">{children}</div>
    </section>
  );
}
