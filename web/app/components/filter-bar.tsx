"use client";

import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

import { ayLabel } from "@/lib/ay";

// Each consumer page opts into the fields it needs by passing the
// corresponding prop. Omit a prop → that field doesn't render.
// Designed so a single bar serves Scores (all 5 fields), Approval
// Queue (AY + dates + classroom), and Students (classroom + batch).
//
// `ALL_FILTER` is still exported for the Batch single-select. Course
// is now a multi-select keyed off an array — empty array means "all
// classrooms", matching ALL_FILTER semantics without the sentinel.

export const ALL_FILTER = "ALL";

export type CourseOption = { course_id: string; label: string };
export type BatchOption = { key: string; label: string };

export interface FilterBarProps {
  ay?: {
    value: number;
    options: number[];
    onChange: (n: number) => void;
  };
  dateFrom?: { value: string; onChange: (s: string) => void };
  dateTo?: { value: string; onChange: (s: string) => void };
  course?: {
    value: string[]; // selected course_ids; [] = all classrooms
    options: CourseOption[];
    onChange: (next: string[]) => void;
  };
  batch?: {
    value: string; // batch key or ALL_FILTER
    options: BatchOption[];
    onChange: (s: string) => void;
  };
}

export function FilterBar(props: FilterBarProps) {
  const fieldCount =
    (props.ay ? 1 : 0) +
    (props.dateFrom ? 1 : 0) +
    (props.dateTo ? 1 : 0) +
    (props.course ? 1 : 0) +
    (props.batch ? 1 : 0);
  if (fieldCount === 0) return null;
  // Static class strings so Tailwind's JIT picks them up — avoids the
  // pitfall of constructing class names at runtime (would otherwise be
  // purged from the build).
  const lgColsCls =
    fieldCount >= 5
      ? "lg:grid-cols-5"
      : fieldCount === 4
        ? "lg:grid-cols-4"
        : fieldCount === 3
          ? "lg:grid-cols-3"
          : fieldCount === 2
            ? "lg:grid-cols-2"
            : "lg:grid-cols-1";
  return (
    <div
      className={`grid grid-cols-1 gap-3 rounded-xl border border-ink-10 bg-[rgba(24,24,27,0.55)] p-4 md:grid-cols-2 ${lgColsCls}`}
    >
      {props.ay && (
        <Field label="Academic Year">
          <select
            value={props.ay.value}
            onChange={(e) => props.ay!.onChange(Number(e.target.value))}
            className={SELECT_CLS}
          >
            {props.ay.options.map((y) => (
              <option key={y} value={y}>
                {ayLabel(y)}
              </option>
            ))}
          </select>
        </Field>
      )}

      {props.dateFrom && (
        <Field label="Date From">
          <input
            type="date"
            value={props.dateFrom.value}
            onChange={(e) => props.dateFrom!.onChange(e.target.value)}
            // Safari (and a few other browsers) don't auto-open the
            // calendar overlay on a plain click of <input type="date">.
            // showPicker() — Chrome 99+, Safari 16.4+, Firefox 101+ —
            // forces it open; the optional chain no-ops on older.
            onClick={(e) => e.currentTarget.showPicker?.()}
            className={DATE_CLS}
          />
        </Field>
      )}

      {props.dateTo && (
        <Field label="Date To">
          <input
            type="date"
            value={props.dateTo.value}
            onChange={(e) => props.dateTo!.onChange(e.target.value)}
            onClick={(e) => e.currentTarget.showPicker?.()}
            className={DATE_CLS}
          />
        </Field>
      )}

      {props.course && (
        <Field label="Classroom">
          <MultiSelectDropdown
            options={props.course.options.map((c) => ({
              key: c.course_id,
              label: c.label,
            }))}
            values={props.course.value}
            onChange={props.course.onChange}
            allLabel="All classrooms"
            singularLabel="classroom"
            pluralLabel="classrooms"
          />
        </Field>
      )}

      {props.batch && (
        <Field label="Batch">
          <select
            value={props.batch.value}
            onChange={(e) => props.batch!.onChange(e.target.value)}
            disabled={props.batch.options.length === 0}
            className={`${SELECT_CLS} disabled:opacity-50`}
          >
            <option value={ALL_FILTER}>
              {props.batch.options.length === 0 ? "No batches" : "All batches"}
            </option>
            {props.batch.options.map((b) => (
              <option key={b.key} value={b.key}>
                {b.label}
              </option>
            ))}
          </select>
        </Field>
      )}
    </div>
  );
}

const SELECT_CLS =
  "w-full rounded-md border border-ink-10 bg-ink-5 px-2 py-[7px] font-sans text-[12px] text-ink-100 outline-none focus:border-cyan";
const DATE_CLS =
  "w-full rounded-md border border-ink-10 bg-ink-5 px-2 py-[6px] font-mono text-[12px] text-ink-100 outline-none focus:border-cyan";

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="font-mono text-[9.5px] uppercase tracking-[0.2em] text-ink-40">
        {label}
      </span>
      {children}
    </label>
  );
}

// ─────────────────────────────────────────────────────────────────────
// Multi-select dropdown with checkbox popover. Empty `values` = "all";
// trigger label adapts to the selection count.
// ─────────────────────────────────────────────────────────────────────

type MultiOption = { key: string; label: string };

function MultiSelectDropdown({
  options,
  values,
  onChange,
  allLabel,
  singularLabel,
  pluralLabel,
}: {
  options: MultiOption[];
  values: string[];
  onChange: (next: string[]) => void;
  allLabel: string;
  singularLabel: string;
  pluralLabel: string;
}) {
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (!wrapperRef.current) return;
      if (!wrapperRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("mousedown", onClick);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", onClick);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const triggerLabel =
    values.length === 0
      ? allLabel
      : values.length === 1
        ? (options.find((o) => o.key === values[0])?.label ?? `1 ${singularLabel}`)
        : `${values.length} ${pluralLabel} selected`;

  function toggle(k: string) {
    if (values.includes(k)) onChange(values.filter((v) => v !== k));
    else onChange([...values, k]);
  }

  return (
    <div ref={wrapperRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        disabled={options.length === 0}
        className={`flex w-full items-center justify-between gap-2 rounded-md border border-ink-10 bg-ink-5 px-2 py-[7px] font-sans text-[12px] text-left text-ink-100 outline-none transition focus:border-cyan disabled:opacity-50 ${
          open ? "border-cyan" : ""
        }`}
      >
        <span className="truncate">
          {options.length === 0 ? `No ${pluralLabel}` : triggerLabel}
        </span>
        <svg
          width="10"
          height="10"
          viewBox="0 0 12 12"
          fill="none"
          aria-hidden
          className={`shrink-0 transition ${open ? "rotate-180" : ""}`}
        >
          <path
            d="M3 4.5 6 7.5 9 4.5"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>
      {open && (
        <div className="glass-strong absolute left-0 right-0 top-[calc(100%+4px)] z-50 max-h-[320px] overflow-y-auto rounded-md border border-ink-10 shadow-2xl">
          <div className="sticky top-0 z-10 flex items-center justify-between gap-2 border-b border-ink-10 bg-[rgba(24,24,27,0.95)] px-3 py-2">
            <button
              type="button"
              onClick={() => onChange([])}
              className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-40 hover:text-ink-100"
            >
              All
            </button>
            <button
              type="button"
              onClick={() => onChange(options.map((o) => o.key))}
              className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-40 hover:text-ink-100"
            >
              Select all
            </button>
          </div>
          <ul className="py-1">
            {options.map((opt) => {
              const checked = values.includes(opt.key);
              return (
                <li key={opt.key}>
                  <label className="flex cursor-pointer items-center gap-2 px-3 py-1.5 transition hover:bg-[rgba(34,211,238,0.08)]">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggle(opt.key)}
                      className="h-3.5 w-3.5 accent-[var(--cyan)]"
                    />
                    <span className="truncate font-sans text-[12px] text-ink-100">
                      {opt.label}
                    </span>
                  </label>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}

// Summary line that consumers can render below the filter bar. Each
// stat is optional so the line stays terse on pages that only filter
// on a subset.
export function FilterSummary(props: {
  items?: { count: number; label: string };
  students?: number;
  assignments?: number;
  dateFrom?: string;
  dateTo?: string;
}) {
  const parts: ReactNode[] = [];
  if (props.items) {
    parts.push(
      <span key="items">
        <span className="text-ink-80">{props.items.count}</span> {props.items.label}
      </span>,
    );
  }
  if (typeof props.students === "number") {
    parts.push(
      <span key="students">
        <span className="text-ink-80">{props.students}</span> students
      </span>,
    );
  }
  if (typeof props.assignments === "number") {
    parts.push(
      <span key="assignments">
        <span className="text-ink-80">{props.assignments}</span> assignments
      </span>,
    );
  }
  if (props.dateFrom && props.dateTo) {
    parts.push(
      <span key="dates" className="normal-case tracking-normal">
        {props.dateFrom} → {props.dateTo}
      </span>,
    );
  }
  if (parts.length === 0) return null;
  const interleaved: ReactNode[] = [];
  parts.forEach((p, i) => {
    if (i > 0) {
      interleaved.push(
        <span key={`sep-${i}`} aria-hidden>
          ·
        </span>,
      );
    }
    interleaved.push(p);
  });
  return (
    <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[10.5px] uppercase tracking-[0.18em] text-ink-40">
      {interleaved}
    </div>
  );
}
