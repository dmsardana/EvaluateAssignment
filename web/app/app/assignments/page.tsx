"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import useSWR from "swr";

import {
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  StatusPill,
  TypePill,
} from "@/components/page-chrome";
import { api, AssignmentType, QueueItem } from "@/lib/api";

const TYPE_ORDER: AssignmentType[] = ["WA", "QA", "AA", "ZA"];
const TYPE_LABEL: Record<AssignmentType, string> = {
  WA: "Worksheet",
  QA: "Quarterly",
  AA: "Annual",
  ZA: "Diagnostic",
};

export default function AssignmentsPage() {
  const router = useRouter();
  const { data, error, isLoading } = useSWR<QueueItem[]>(
    "/api/queue",
    () => api.queue(),
    { refreshInterval: 30_000 },
  );

  const items = data ?? [];
  const grouped: Record<AssignmentType, QueueItem[]> = {
    WA: [],
    QA: [],
    AA: [],
    ZA: [],
  };
  for (const it of items) grouped[it.assignment_type].push(it);
  for (const t of TYPE_ORDER) {
    grouped[t].sort((a, b) =>
      (b.generated_at ?? "").localeCompare(a.generated_at ?? ""),
    );
  }

  return (
    <div>
      <PageHeader
        eyebrow="Console · Assignments"
        title="Every assignment, ever."
        lede="Grouped by tier. Click any row to see submissions, model used, and per-question status."
      />
      {isLoading && <LoadingState label="loading assignments" />}
      {error && <ErrorState error={error} />}
      {!isLoading && !error && items.length === 0 && (
        <EmptyState title="No assignments detected yet." />
      )}

      <div className="px-6 py-8 md:px-10">
        {TYPE_ORDER.map((t) =>
          grouped[t].length > 0 ? (
            <section key={t} className="mb-10">
              <div className="mb-4 flex items-baseline gap-3">
                <TypePill type={t} />
                <h2 className="font-display text-[22px] text-ink-100">
                  {TYPE_LABEL[t]}
                </h2>
                <span className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-ink-40">
                  {grouped[t].length} item{grouped[t].length === 1 ? "" : "s"}
                </span>
              </div>
              <div className="overflow-hidden rounded-xl border border-ink-10">
                <table className="w-full border-collapse text-left text-[13px]">
                  <thead className="bg-[rgba(24,24,27,0.6)] text-ink-40">
                    <tr>
                      <Th>Code</Th>
                      <Th>Title</Th>
                      <Th>Status</Th>
                      <Th className="text-right">Submissions</Th>
                      <Th className="text-right">Questions</Th>
                      <Th>Generated</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {grouped[t].map((it, i) => (
                      <tr
                        key={it.coursework_id}
                        // Whole row navigates — clicking anywhere in the
                        // ribbon opens the assignment, not just the title.
                        // Enter key handler keeps it keyboard-accessible.
                        tabIndex={0}
                        role="link"
                        onClick={() => router.push(`/queue/${it.coursework_id}`)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            router.push(`/queue/${it.coursework_id}`);
                          }
                        }}
                        className={`cursor-pointer border-t border-ink-10 transition hover:bg-[rgba(248,113,113,0.05)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[var(--cyan)] ${
                          i % 2 === 0 ? "" : "bg-[rgba(24,24,27,0.35)]"
                        }`}
                      >
                        <Td className="font-mono text-[12px] text-ink-100">
                          {it.assignment_code}
                        </Td>
                        <Td className="text-ink-80">
                          {it.assignment_title || "—"}
                        </Td>
                        <Td>
                          <StatusPill status={it.status} />
                        </Td>
                        <Td className="text-right tabular-nums text-ink-80">
                          {it.submission_count}
                        </Td>
                        <Td className="text-right tabular-nums text-ink-80">
                          {it.questions_count}
                        </Td>
                        <Td className="font-mono text-[11px] text-ink-40">
                          {it.generated_at
                            ? new Date(it.generated_at).toLocaleDateString()
                            : "—"}
                        </Td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ) : null,
        )}
      </div>

      <div className="border-t border-ink-10 px-6 py-6 md:px-10">
        <Link
          href="/"
          className="font-mono text-[11px] uppercase tracking-[0.2em] text-ink-40 hover:text-ink-100"
        >
          ← Back to approval queue
        </Link>
      </div>
    </div>
  );
}

function Th({
  children,
  className = "",
}: {
  children: React.ReactNode;
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
  children: React.ReactNode;
  className?: string;
}) {
  return <td className={`px-4 py-3 ${className}`}>{children}</td>;
}
