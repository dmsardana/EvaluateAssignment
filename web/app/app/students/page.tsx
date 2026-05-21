"use client";

import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";

import {
  ALL_FILTER,
  FilterBar,
  FilterSummary,
} from "@/components/filter-bar";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
} from "@/components/page-chrome";
import { api, StudentProfile } from "@/lib/api";

export default function StudentsPage() {
  const { data, error, isLoading } = useSWR<StudentProfile[]>(
    "/api/students",
    () => api.students(),
    { refreshInterval: 60_000 },
  );
  const [query, setQuery] = useState("");
  const [courseFilter, setCourseFilter] = useState<string[]>([]);
  const [batchFilter, setBatchFilter] = useState<string>(ALL_FILTER);

  const students = data ?? [];

  // Reset batch when the set of selected classrooms changes — sections
  // are scoped to a course and otherwise become stale.
  useEffect(() => {
    setBatchFilter(ALL_FILTER);
  }, [courseFilter]);

  // Unique courses across the whole roster, for the Classroom dropdown.
  const courseOptions = useMemo(() => {
    const seen = new Map<string, string>();
    for (const s of students) {
      for (const c of s.courses) {
        if (!seen.has(c.course_id)) seen.set(c.course_id, c.label);
      }
    }
    return [...seen.entries()]
      .map(([course_id, label]) => ({ course_id, label }))
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [students]);

  // Batch options scoped to the currently-selected classrooms (or all
  // when no classrooms are selected).
  const batchOptions = useMemo(() => {
    const selected = new Set(courseFilter);
    const limitToSelected = selected.size > 0;
    const out = new Map<string, string>();
    for (const s of students) {
      for (const c of s.courses) {
        if (limitToSelected && !selected.has(c.course_id)) continue;
        const section = (c.section || "").trim();
        if (!section) continue;
        const key = `${c.course_id}::${section}`;
        if (!out.has(key)) out.set(key, section);
      }
    }
    return [...out.entries()]
      .map(([key, label]) => ({ key, label }))
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [students, courseFilter]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const selected = new Set(courseFilter);
    let list = students.filter((s) => {
      if (selected.size > 0) {
        if (!s.courses.some((c) => selected.has(c.course_id))) return false;
      }
      if (batchFilter !== ALL_FILTER) {
        const [batchCourse, batchSection] = batchFilter.split("::");
        const ok = s.courses.some(
          (c) =>
            c.course_id === batchCourse && (c.section || "") === batchSection,
        );
        if (!ok) return false;
      }
      return true;
    });
    if (q) {
      list = list.filter(
        (s) =>
          s.student_name.toLowerCase().includes(q) ||
          (s.display_name ?? "").toLowerCase().includes(q) ||
          (s.email ?? "").toLowerCase().includes(q) ||
          s.courses.some((c) => c.label.toLowerCase().includes(q)),
      );
    }
    return [...list].sort((a, b) =>
      (a.display_name || a.student_name).localeCompare(
        b.display_name || b.student_name,
      ),
    );
  }, [students, query, courseFilter, batchFilter]);

  const inRoster = filtered.filter((s) => s.in_roster).length;

  return (
    <div>
      <PageHeader
        eyebrow="Console · Students"
        title="The roster."
        lede="Live from Google Classroom. Display name overrides the roster name on reports."
        actions={
          <div className="flex items-center gap-3">
            <span className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-ink-40">
              {inRoster}/{filtered.length} in roster
            </span>
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search…"
              className="w-56 rounded-lg border border-ink-10 bg-ink-5 px-3 py-[7px] font-sans text-[12px] text-ink-100 outline-none focus:border-cyan"
            />
          </div>
        }
      />

      <section className="px-6 pb-4 md:px-10">
        <FilterBar
          course={{
            value: courseFilter,
            options: courseOptions,
            onChange: setCourseFilter,
          }}
          batch={{
            value: batchFilter,
            options: batchOptions,
            onChange: setBatchFilter,
          }}
        />
        <FilterSummary items={{ count: filtered.length, label: "students" }} />
      </section>

      {isLoading && <LoadingState label="loading students" />}
      {error && <ErrorState error={error} />}
      {!isLoading && !error && students.length === 0 && (
        <EmptyState title="No students found." />
      )}
      {!isLoading && !error && students.length > 0 && filtered.length === 0 && (
        <EmptyState title="No students match these filters." />
      )}

      {filtered.length > 0 && (
        <div className="px-6 py-8 md:px-10">
          <div className="overflow-hidden rounded-xl border border-ink-10">
            <table className="w-full border-collapse text-left text-[13px]">
              <thead className="bg-[rgba(24,24,27,0.6)] text-ink-40">
                <tr>
                  <Th>Name</Th>
                  <Th>Display</Th>
                  <Th>Email</Th>
                  <Th>Mobile</Th>
                  <Th>Classroom</Th>
                  <Th>State</Th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((s, i) => (
                  <tr
                    key={s.student_id}
                    className={`border-t border-ink-10 transition hover:bg-[rgba(248,113,113,0.05)] ${
                      i % 2 === 0 ? "" : "bg-[rgba(24,24,27,0.35)]"
                    }`}
                  >
                    <Td className="text-ink-100">{s.student_name}</Td>
                    <Td className="text-ink-80">
                      {s.display_name ? (
                        <span className="italic">{s.display_name}</span>
                      ) : (
                        <span className="text-ink-40">—</span>
                      )}
                    </Td>
                    <Td className="font-mono text-[11px] text-ink-40">
                      {s.email || "—"}
                    </Td>
                    <Td className="font-mono text-[11px] text-ink-40">
                      {s.mobile || "—"}
                    </Td>
                    <Td>
                      <div className="flex flex-wrap gap-1">
                        {s.courses.length === 0 ? (
                          <span className="text-ink-40">—</span>
                        ) : (
                          s.courses.map((c) => (
                            <span
                              key={c.course_id}
                              className="inline-flex items-center rounded border border-ink-10 bg-ink-5 px-2 py-[2px] font-mono text-[10px] text-ink-80"
                              title={c.name}
                            >
                              {c.label}
                            </span>
                          ))
                        )}
                      </div>
                    </Td>
                    <Td>
                      {s.in_roster ? (
                        <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--lime)]">
                          in roster
                        </span>
                      ) : (
                        <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-40">
                          removed
                        </span>
                      )}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
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
