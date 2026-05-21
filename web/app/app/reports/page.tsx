"use client";

import { useMemo, useState } from "react";
import useSWR from "swr";

import {
  BAND_STYLE,
  BandPill,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  TypePill,
} from "@/components/page-chrome";
import { api, AssignmentType, Band, ReportRow } from "@/lib/api";

const TYPE_FILTERS: (AssignmentType | "ALL")[] = ["ALL", "WA", "QA", "AA", "ZA"];
const BAND_FILTERS: (Band | "ALL")[] = [
  "ALL",
  "TRBLZ",
  "QUALIF",
  "DEVLP",
  "F-GAPS",
];

export default function ReportsPage() {
  const { data, error, isLoading } = useSWR<ReportRow[]>(
    "/api/reports",
    () => api.reports(),
    { refreshInterval: 60_000 },
  );

  const [typeFilter, setTypeFilter] = useState<(typeof TYPE_FILTERS)[number]>(
    "ALL",
  );
  const [bandFilter, setBandFilter] = useState<(typeof BAND_FILTERS)[number]>(
    "ALL",
  );

  const rows = data ?? [];
  const filtered = useMemo(() => {
    return rows
      .filter((r) => typeFilter === "ALL" || r.assignment_type === typeFilter)
      .filter((r) => bandFilter === "ALL" || r.band === bandFilter)
      .sort((a, b) =>
        (b.evaluation_date ?? "").localeCompare(a.evaluation_date ?? ""),
      );
  }, [rows, typeFilter, bandFilter]);

  const summary = useMemo(() => {
    const out: Record<Band, number> = {
      TRBLZ: 0,
      QUALIF: 0,
      DEVLP: 0,
      "F-GAPS": 0,
    };
    for (const r of filtered) out[r.band] += 1;
    return out;
  }, [filtered]);

  return (
    <div>
      <PageHeader
        eyebrow="Console · Reports"
        title="Graded reports."
        lede="One row per (student × assignment). Click the title to open the PDF on Drive."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <FilterChips
              options={TYPE_FILTERS}
              value={typeFilter}
              onChange={setTypeFilter}
            />
            <FilterChips
              options={BAND_FILTERS}
              value={bandFilter}
              onChange={setBandFilter}
              label="band"
            />
          </div>
        }
      />

      {isLoading && <LoadingState label="loading reports" />}
      {error && <ErrorState error={error} />}
      {!isLoading && !error && rows.length === 0 && (
        <EmptyState
          title="No reports yet."
          hint="Once an evaluation completes, the PDF lands here."
        />
      )}

      {filtered.length > 0 && (
        <>
          <div className="grid grid-cols-2 gap-3 px-6 pt-6 sm:grid-cols-4 md:px-10">
            {(["TRBLZ", "QUALIF", "DEVLP", "F-GAPS"] as Band[]).map((b) => {
              const s = BAND_STYLE[b];
              return (
                <div
                  key={b}
                  className="rounded-xl border border-ink-10 bg-[rgba(24,24,27,0.55)] p-4"
                >
                  <div
                    className={`font-mono text-[10.5px] uppercase tracking-[0.18em] ${s.fg}`}
                  >
                    {s.label}
                  </div>
                  <div className="mt-1 font-display text-[28px] tabular-nums text-ink-100">
                    {summary[b]}
                  </div>
                </div>
              );
            })}
          </div>

          <div className="px-6 py-8 md:px-10">
            <div className="overflow-hidden rounded-xl border border-ink-10">
              <table className="w-full border-collapse text-left text-[13px]">
                <thead className="bg-[rgba(24,24,27,0.6)] text-ink-40">
                  <tr>
                    <Th>Student</Th>
                    <Th>Type</Th>
                    <Th>Title</Th>
                    <Th>Band</Th>
                    <Th className="text-right">Score</Th>
                    <Th>Evaluated</Th>
                    <Th>PDF</Th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((r, i) => (
                    <tr
                      key={`${r.student_id}-${r.coursework_id}-${i}`}
                      className={`border-t border-ink-10 transition hover:bg-[rgba(248,113,113,0.05)] ${
                        i % 2 === 0 ? "" : "bg-[rgba(24,24,27,0.35)]"
                      }`}
                    >
                      <Td className="text-ink-100">{r.student_name}</Td>
                      <Td>
                        <div className="flex items-center gap-2">
                          <TypePill type={r.assignment_type} />
                          <span className="font-mono text-[11px] text-ink-40">
                            {r.assignment_code}
                          </span>
                        </div>
                      </Td>
                      <Td className="text-ink-80">
                        {r.assignment_title || "—"}
                      </Td>
                      <Td>
                        <BandPill band={r.band} />
                      </Td>
                      <Td className="text-right font-mono tabular-nums text-ink-100">
                        {r.percentage.toFixed(1)}%
                      </Td>
                      <Td className="font-mono text-[11px] text-ink-40">
                        {r.evaluation_date}
                      </Td>
                      <Td>
                        <a
                          href={r.report_url}
                          target="_blank"
                          rel="noreferrer"
                          className="font-mono text-[11px] uppercase tracking-[0.16em] text-[var(--cyan)] hover:text-ink-100"
                        >
                          Open ↗
                        </a>
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function FilterChips<T extends string>({
  options,
  value,
  onChange,
  label,
}: {
  options: readonly T[];
  value: T;
  onChange: (v: T) => void;
  label?: string;
}) {
  return (
    <div className="flex items-center gap-1 rounded-lg border border-ink-10 bg-ink-5 p-1">
      {label && (
        <span className="px-2 font-mono text-[9.5px] uppercase tracking-[0.18em] text-ink-40">
          {label}
        </span>
      )}
      {options.map((o) => (
        <button
          key={o}
          type="button"
          onClick={() => onChange(o)}
          className={`rounded-md px-2 py-[3px] font-mono text-[10.5px] uppercase tracking-[0.14em] transition ${
            value === o
              ? "bg-ink-10 text-ink-100"
              : "text-ink-40 hover:text-ink-100"
          }`}
        >
          {o}
        </button>
      ))}
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
