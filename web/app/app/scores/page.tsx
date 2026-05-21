"use client";

import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";

import {
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  TypePill,
} from "@/components/page-chrome";
import {
  ALL_FILTER,
  FilterBar,
  FilterSummary,
} from "@/components/filter-bar";
import {
  api,
  ScoreMatrixAssignment,
  ScoreMatrixResponse,
  ScoreMatrixStudent,
} from "@/lib/api";
import {
  ayRange,
  ayStartYear,
  defaultAyOptions,
  parseDate,
  unionAyOptions,
} from "@/lib/ay";

function pctTone(p: number | undefined): string {
  if (p === undefined) return "text-ink-40";
  if (p >= 75) return "text-[var(--lime)]";
  if (p >= 60) return "text-[var(--cyan)]";
  if (p >= 45) return "text-[var(--magenta)]";
  return "text-[var(--ts-red)]";
}

export default function ScoresPage() {
  const { data, error, isLoading } = useSWR<ScoreMatrixResponse>(
    "/api/scores-matrix",
    () => api.scoresMatrix(),
    { refreshInterval: 60_000 },
  );

  const today = useMemo(() => new Date(), []);
  const currentAyStart = useMemo(() => ayStartYear(today), [today]);
  const ayOptions = useMemo(() => {
    // Always offer a generous AY range so operators can pick past or
    // future years even when no assignments live there yet. Observed
    // AYs from the data are unioned on top so newly-discovered years
    // (e.g. when older data syncs in) still show up.
    const observed: number[] = [];
    for (const a of data?.assignments ?? []) {
      const d = parseDate(a.evaluation_date);
      if (d) observed.push(ayStartYear(d));
    }
    return unionAyOptions(defaultAyOptions(today), observed);
  }, [data, today]);

  const [ay, setAy] = useState<number>(currentAyStart);
  const initial = ayRange(currentAyStart);
  const [dateFrom, setDateFrom] = useState<string>(initial.from);
  const [dateTo, setDateTo] = useState<string>(initial.to);
  const [courseFilter, setCourseFilter] = useState<string[]>([]);
  const [batchFilter, setBatchFilter] = useState<string>(ALL_FILTER);

  useEffect(() => {
    const r = ayRange(ay);
    setDateFrom(r.from);
    setDateTo(r.to);
  }, [ay]);

  useEffect(() => {
    // Reset batch when the set of selected classrooms changes — sections
    // are scoped to a course and otherwise become stale.
    setBatchFilter(ALL_FILTER);
  }, [courseFilter]);

  const matrix = data;

  const batchOptions = useMemo(() => {
    if (!matrix) return [] as { key: string; label: string }[];
    const selected = new Set(courseFilter);
    const limitToSelected = selected.size > 0;
    const out = new Map<string, string>();
    for (const s of matrix.students) {
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
  }, [matrix, courseFilter]);

  const filteredAssignments = useMemo(() => {
    if (!matrix) return [] as ScoreMatrixAssignment[];
    const from = parseDate(dateFrom);
    const to = parseDate(dateTo);
    const list = matrix.assignments.filter((a) => {
      const d = parseDate(a.evaluation_date);
      if (!d) return true;
      if (from && d < from) return false;
      if (to && d > to) return false;
      return true;
    });
    return list.sort((a, b) => {
      const da = parseDate(a.evaluation_date)?.getTime() ?? Infinity;
      const db = parseDate(b.evaluation_date)?.getTime() ?? Infinity;
      return da - db;
    });
  }, [matrix, dateFrom, dateTo]);

  const filteredStudents = useMemo(() => {
    if (!matrix) return [] as ScoreMatrixStudent[];
    const selected = new Set(courseFilter);
    const list = matrix.students.filter((s) => {
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
    return [...list].sort((a, b) =>
      (a.display_name || a.student_name).localeCompare(
        b.display_name || b.student_name,
      ),
    );
  }, [matrix, courseFilter, batchFilter]);

  return (
    <div>
      <PageHeader
        eyebrow="Console · Scores"
        title="The matrix."
        lede="Pivot of every student × every graded assignment, filtered by AY, date range, classroom and batch."
      />

      <section className="px-6 pb-4 md:px-10">
        <FilterBar
          ay={{ value: ay, options: ayOptions, onChange: setAy }}
          dateFrom={{ value: dateFrom, onChange: setDateFrom }}
          dateTo={{ value: dateTo, onChange: setDateTo }}
          course={{
            value: courseFilter,
            options: matrix?.courses ?? [],
            onChange: setCourseFilter,
          }}
          batch={{
            value: batchFilter,
            options: batchOptions,
            onChange: setBatchFilter,
          }}
        />
        <FilterSummary
          students={filteredStudents.length}
          assignments={filteredAssignments.length}
          dateFrom={dateFrom}
          dateTo={dateTo}
        />
      </section>

      {isLoading && <LoadingState label="building matrix" />}
      {error && <ErrorState error={error} />}
      {!isLoading &&
        !error &&
        matrix &&
        (filteredStudents.length === 0 ? (
          <EmptyState title="No students match these filters." />
        ) : filteredAssignments.length === 0 ? (
          <EmptyState title="No assignments in this date range." />
        ) : (
          <div className="px-6 pb-8 md:px-10">
            <div className="overflow-x-auto rounded-xl border border-ink-10">
              <table className="min-w-full border-collapse text-left text-[12px]">
                <thead>
                  <tr className="bg-[rgba(24,24,27,0.7)]">
                    <th className="sticky left-0 z-10 min-w-[220px] bg-[rgba(24,24,27,0.95)] px-4 py-3 font-mono text-[10px] font-medium uppercase tracking-[0.18em] text-ink-40">
                      Student
                    </th>
                    {filteredAssignments.map((a) => (
                      <th
                        key={a.key}
                        className="min-w-[110px] border-l border-ink-10 px-3 py-2 text-center"
                        title={a.assignment_title}
                      >
                        <div className="flex flex-col items-center gap-1">
                          <TypePill type={a.assignment_type} />
                          <span className="font-mono text-[10px] text-ink-80">
                            {a.assignment_code}
                          </span>
                          {a.evaluation_date && (
                            <span className="font-mono text-[9px] text-ink-40">
                              {a.evaluation_date}
                            </span>
                          )}
                        </div>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filteredStudents.map((s, i) => {
                    const row = matrix.cells[s.student_id] ?? {};
                    return (
                      <tr
                        key={s.student_id}
                        className={`border-t border-ink-10 transition hover:bg-[rgba(248,113,113,0.04)] ${
                          i % 2 === 0 ? "" : "bg-[rgba(24,24,27,0.3)]"
                        }`}
                      >
                        <th
                          scope="row"
                          className="sticky left-0 z-10 bg-[#0c0c0e] px-4 py-3 text-left font-medium text-ink-100"
                        >
                          <div>{s.display_name || s.student_name}</div>
                          <div className="mt-1 flex flex-wrap gap-1">
                            {s.courses.slice(0, 2).map((c) => (
                              <span
                                key={c.course_id}
                                className="rounded border border-ink-10 bg-ink-5 px-1.5 py-[1px] font-mono text-[9px] text-ink-40"
                              >
                                {c.label}
                              </span>
                            ))}
                          </div>
                        </th>
                        {filteredAssignments.map((a) => {
                          const cell = row[a.key];
                          return (
                            <td
                              key={a.key}
                              className="border-l border-ink-10 px-3 py-3 text-center"
                            >
                              {cell ? (
                                <div className="flex flex-col items-center">
                                  <span
                                    className={`font-mono text-[14px] font-semibold tabular-nums ${pctTone(cell.percentage)}`}
                                  >
                                    {cell.percentage.toFixed(0)}%
                                  </span>
                                  <span className="font-mono text-[9px] text-ink-40">
                                    {cell.earned.toFixed(1)}/{cell.max.toFixed(0)}
                                  </span>
                                </div>
                              ) : (
                                <span className="font-mono text-[11px] text-ink-40">
                                  —
                                </span>
                              )}
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        ))}
    </div>
  );
}
