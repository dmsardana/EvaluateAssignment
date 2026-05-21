"use client";

import Link from "next/link";
import { useMemo } from "react";
import useSWR from "swr";

import {
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  StatusPill,
  TypePill,
} from "@/components/page-chrome";
import { api, QueueItem } from "@/lib/api";

interface CourseSummary {
  course_id: string;
  item_count: number;
  most_recent: string | null;
  by_status: Record<string, number>;
  examples: QueueItem[];
}

function summarise(items: QueueItem[]): CourseSummary[] {
  const map = new Map<string, CourseSummary>();
  for (const it of items) {
    const c = map.get(it.course_id) ?? {
      course_id: it.course_id,
      item_count: 0,
      most_recent: null,
      by_status: {},
      examples: [],
    };
    c.item_count += 1;
    c.by_status[it.status] = (c.by_status[it.status] ?? 0) + 1;
    if (
      it.generated_at &&
      (c.most_recent === null || it.generated_at > c.most_recent)
    ) {
      c.most_recent = it.generated_at;
    }
    if (c.examples.length < 3) c.examples.push(it);
    map.set(it.course_id, c);
  }
  return [...map.values()].sort((a, b) =>
    (b.most_recent ?? "").localeCompare(a.most_recent ?? ""),
  );
}

export default function ClassroomSettingsPage() {
  const { data, error, isLoading } = useSWR<QueueItem[]>("/api/queue", () =>
    api.queue(),
  );
  const courses = useMemo(() => summarise(data ?? []), [data]);

  return (
    <div>
      <PageHeader
        eyebrow="Settings · Classroom"
        title="Wired courses."
        lede="Derived from every coursework detected on Google Classroom. Reconnect via Credentials if a course goes missing."
        actions={
          <Link
            href="/settings/credentials"
            className="rounded-md border border-ink-10 bg-ink-5 px-3 py-[6px] font-sans text-[12px] text-ink-100 hover:border-[rgba(34,211,238,0.4)]"
          >
            Reconnect Google →
          </Link>
        }
      />

      {isLoading && <LoadingState label="reading queue" />}
      {error && <ErrorState error={error} />}
      {!isLoading && !error && courses.length === 0 && (
        <EmptyState title="No Classroom courses detected." />
      )}

      {courses.length > 0 && (
        <div className="px-6 py-8 md:px-10">
          <div className="grid gap-3">
            {courses.map((c) => (
              <article
                key={c.course_id}
                className="rounded-xl border border-ink-10 bg-[rgba(24,24,27,0.55)] p-5"
              >
                <div className="flex flex-wrap items-baseline justify-between gap-3">
                  <div>
                    <div className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-ink-40">
                      course id
                    </div>
                    <div className="mt-1 font-display text-[20px] text-ink-100">
                      {c.course_id}
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-[10.5px] uppercase tracking-[0.18em] text-ink-40">
                      {c.item_count} item{c.item_count === 1 ? "" : "s"}
                    </span>
                    {c.most_recent && (
                      <span className="font-mono text-[10.5px] text-ink-40">
                        last · {new Date(c.most_recent).toLocaleDateString()}
                      </span>
                    )}
                  </div>
                </div>

                <div className="mt-3 flex flex-wrap gap-1.5">
                  {Object.entries(c.by_status)
                    .sort(([, a], [, b]) => b - a)
                    .map(([st, n]) => (
                      <span key={st} className="inline-flex items-center gap-1">
                        <StatusPill status={st} />
                        <span className="font-mono text-[10.5px] tabular-nums text-ink-80">
                          {n}
                        </span>
                      </span>
                    ))}
                </div>

                <ul className="mt-4 space-y-1 border-t border-ink-10 pt-3">
                  {c.examples.map((it) => (
                    <li
                      key={it.coursework_id}
                      className="flex items-center gap-3 text-[13px]"
                    >
                      <TypePill type={it.assignment_type} />
                      <span className="font-mono text-[11px] text-ink-40">
                        {it.assignment_code}
                      </span>
                      <Link
                        href={`/queue/${it.coursework_id}`}
                        className="truncate text-ink-80 hover:text-ink-100"
                      >
                        {it.assignment_title || "(untitled)"}
                      </Link>
                    </li>
                  ))}
                </ul>
              </article>
            ))}
          </div>

          <div className="mt-8 rounded-xl border border-dashed border-ink-10 bg-[rgba(24,24,27,0.4)] p-5 text-[13px] text-ink-40">
            Course names + section labels come from{" "}
            <span className="font-mono">/api/students.courses</span>; that
            endpoint is currently returning 500 from FastAPI, so this page shows
            raw course IDs only until the backend bug is fixed.
          </div>
        </div>
      )}
    </div>
  );
}
