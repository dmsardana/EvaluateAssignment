"use client";

import { useRouter } from "next/navigation";
import {
  KeyboardEvent as ReactKeyboardEvent,
  MouseEvent as ReactMouseEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import useSWR from "swr";

import { api, QueueItem, StudentProfile } from "@/lib/api";

import { PipelinePill } from "./pipeline-pill";
import { UserMenu } from "./user-menu";

function BrandMark() {
  // Real ThinkingSouls mark — sourced from tools/templates/logo.png (the
  // same asset baked into the LaTeX report header) and copied to
  // web/app/public/ so Next.js serves it as a static asset.
  return (
    <img
      src="/ts-logo.png"
      alt="ThinkingSouls"
      width={40}
      height={40}
      className="h-10 w-10 object-contain"
    />
  );
}

export function TopBar({ onMenuClick }: { onMenuClick?: () => void } = {}) {
  const [awaiting, setAwaiting] = useState<number | null>(null);
  // Poll lightly so the chip updates after a generation finishes / approval lands.
  // /api/queue is server-cached for 30s so this is cheap.
  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const items = await api.queue();
        if (!cancelled)
          setAwaiting(
            items.filter(
              (i) => i.status === "PENDING_REVIEW" || i.status === "NEEDS_REGEN",
            ).length,
          );
      } catch {
        /* silent — chip just won't show */
      }
    };
    tick();
    const id = setInterval(tick, 15000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);
  return (
    <header className="glass-strong relative z-10 grid grid-cols-[auto_auto_1fr_auto_auto] items-center gap-3 border-b border-ink-10 px-4 py-4 sm:gap-6 sm:px-6 lg:grid-cols-[auto_1fr_auto_auto] lg:gap-8 lg:px-10">
      <button
        type="button"
        aria-label="Open navigation"
        onClick={onMenuClick}
        className="grid h-9 w-9 place-items-center rounded-lg border border-ink-10 bg-ink-5 text-ink-80 transition hover:bg-ink-10 hover:text-ink-100 lg:hidden"
      >
        <svg width="16" height="16" viewBox="0 0 20 20" fill="none" aria-hidden>
          <path
            d="M3 6h14M3 10h14M3 14h14"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
          />
        </svg>
      </button>

      <a href="/" className="group flex items-center gap-3">
        <div
          className="relative grid h-11 w-11 place-items-center rounded-[12px] transition group-hover:scale-105"
          style={{
            background:
              "radial-gradient(circle at 50% 50%, var(--ts-red-soft), transparent 70%)",
            filter: "drop-shadow(0 0 14px var(--ts-red-glow))",
          }}
        >
          <BrandMark />
        </div>
        <div className="hidden leading-none sm:block">
          <div className="font-display text-[19px] font-bold leading-none tracking-[-0.01em]">
            <span className="text-ink-100">thinking</span>
            <span style={{ color: "var(--ts-red)" }}>Souls</span>
          </div>
          <div className="mt-[6px] font-mono text-[9.5px] font-medium uppercase tracking-[0.2em] text-ink-40">
            Evaluation Console
          </div>
        </div>
      </a>

      <GlobalSearch />

      <div className="flex items-center gap-2">
        {awaiting !== null && awaiting > 0 && (
          <a
            href="/"
            title="Click to jump to the approval queue"
            className="inline-flex items-center gap-[6px] px-2 py-1 font-sans text-[12px] font-semibold transition hover:scale-[1.02] sm:rounded-lg sm:border sm:border-[rgba(236,72,153,0.4)] sm:bg-[linear-gradient(135deg,rgba(236,72,153,0.18),rgba(139,92,246,0.18))] sm:px-[14px] sm:py-[9px] sm:shadow-[0_0_18px_rgba(236,72,153,0.2)]"
            style={{ color: "var(--magenta)" }}
          >
            <span
              aria-hidden
              className="h-[8px] w-[8px] animate-pulse rounded-full sm:h-[6px] sm:w-[6px]"
              style={{
                background: "var(--magenta)",
                boxShadow: "0 0 10px var(--magenta), 0 0 20px rgba(236,72,153,0.55)",
              }}
            />
            <span className="font-mono text-[13px] font-bold tabular-nums sm:font-sans sm:text-[12px]">
              {awaiting}
            </span>
            <span className="hidden sm:inline">awaiting your approval</span>
          </a>
        )}
        <PipelinePill />
      </div>

      <UserMenu />
    </header>
  );
}

// ─────────────────────────────────────────────────────────────────────
// Global search — students, assignments, OTPs.
// ─────────────────────────────────────────────────────────────────────

type SearchHit =
  | {
      kind: "assignment";
      key: string;
      label: string;
      sub: string;
      href: string;
    }
  | {
      kind: "student";
      key: string;
      label: string;
      sub: string;
      href: string;
    }
  | {
      kind: "otp";
      key: string;
      label: string;
      sub: string;
      href: string;
    };

const MAX_RESULTS_PER_GROUP = 4;

function GlobalSearch() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);

  // Reuse SWR caches the data pages already populate — costs nothing
  // when those pages have been visited, falls back to a fetch otherwise.
  const { data: queueItems } = useSWR<QueueItem[]>(
    "/api/queue",
    () => api.queue(),
    { refreshInterval: 60_000 },
  );
  const { data: students } = useSWR<StudentProfile[]>(
    "/api/students",
    () => api.students(),
    { refreshInterval: 120_000 },
  );

  // ⌘K / Ctrl+K focuses the input. Esc closes the dropdown.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const isMod = e.metaKey || e.ctrlKey;
      if (isMod && e.key.toLowerCase() === "k") {
        e.preventDefault();
        inputRef.current?.focus();
        inputRef.current?.select();
        setOpen(true);
      } else if (e.key === "Escape") {
        setOpen(false);
        inputRef.current?.blur();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Close when clicking outside the wrapper.
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (!wrapperRef.current) return;
      if (!wrapperRef.current.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("mousedown", onClick);
    return () => window.removeEventListener("mousedown", onClick);
  }, []);

  const hits = useMemo<SearchHit[]>(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];

    const out: SearchHit[] = [];

    // Assignments — match title or code.
    let assignmentHits = 0;
    for (const i of queueItems ?? []) {
      if (assignmentHits >= MAX_RESULTS_PER_GROUP) break;
      const title = (i.assignment_title || "").toLowerCase();
      const code = (i.assignment_code || "").toLowerCase();
      if (title.includes(q) || code.includes(q)) {
        out.push({
          kind: "assignment",
          key: `a-${i.coursework_id}`,
          label: i.assignment_title || i.assignment_code || "(untitled)",
          sub: `${i.assignment_type} · ${i.assignment_code} · ${i.status}`,
          href: `/queue/${i.coursework_id}`,
        });
        assignmentHits++;
      }
    }

    // OTPs — only on items that actually have one. Match contains.
    let otpHits = 0;
    for (const i of queueItems ?? []) {
      if (otpHits >= MAX_RESULTS_PER_GROUP) break;
      const otp = (i.current_otp || "").toLowerCase();
      if (otp && otp.includes(q)) {
        out.push({
          kind: "otp",
          key: `o-${i.coursework_id}`,
          label: `OTP ${i.current_otp}`,
          sub: `${i.assignment_title || i.assignment_code} · ${i.status}`,
          href: `/queue/${i.coursework_id}`,
        });
        otpHits++;
      }
    }

    // Students — match name, display name, or email.
    let studentHits = 0;
    for (const s of students ?? []) {
      if (studentHits >= MAX_RESULTS_PER_GROUP) break;
      const name = (s.student_name || "").toLowerCase();
      const display = (s.display_name || "").toLowerCase();
      const email = (s.email || "").toLowerCase();
      if (name.includes(q) || display.includes(q) || email.includes(q)) {
        out.push({
          kind: "student",
          key: `s-${s.student_id}`,
          label: s.display_name || s.student_name || s.student_id,
          sub: s.email || s.student_id,
          // No per-student detail route — drop them on /students. A future
          // pass can lift the query to that page's search input.
          href: "/students",
        });
        studentHits++;
      }
    }

    return out;
  }, [query, queueItems, students]);

  const grouped = useMemo(() => {
    const g: Record<SearchHit["kind"], SearchHit[]> = {
      assignment: [],
      otp: [],
      student: [],
    };
    for (const h of hits) g[h.kind].push(h);
    return g;
  }, [hits]);

  function go(href: string) {
    setQuery("");
    setOpen(false);
    router.push(href);
  }

  function onInputKeyDown(e: ReactKeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" && hits.length > 0) {
      e.preventDefault();
      go(hits[0].href);
    }
  }

  return (
    <div
      ref={wrapperRef}
      className="relative hidden max-w-[520px] sm:block"
    >
      <input
        ref={inputRef}
        type="text"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onInputKeyDown}
        placeholder="Search students, assignments, OTPs…"
        className="w-full rounded-[10px] border border-ink-10 bg-ink-5 px-4 py-[11px] pl-10 font-sans text-[13px] text-ink-100 outline-none transition focus:border-cyan focus:shadow-[0_0_0_3px_rgba(34,211,238,0.15)]"
      />
      <div
        className="pointer-events-none absolute left-[14px] top-1/2 h-[14px] w-[14px] -translate-y-1/2 rounded-full border-[1.5px] border-ink-40"
        aria-hidden
      />
      <span className="pointer-events-none absolute right-[10px] top-1/2 -translate-y-1/2 rounded-[5px] border border-ink-10 bg-ink-10 px-[7px] py-[3px] font-mono text-[10px] text-ink-40">
        ⌘ K
      </span>

      {open && query.trim().length > 0 && (
        <div className="glass-strong absolute left-0 right-0 top-[calc(100%+6px)] z-50 max-h-[480px] overflow-y-auto rounded-[10px] border border-ink-10 shadow-2xl">
          {hits.length === 0 ? (
            <div className="px-4 py-6 text-center font-mono text-[11px] text-ink-40">
              No matches for &ldquo;{query}&rdquo;
            </div>
          ) : (
            <div className="py-2">
              <ResultGroup
                title="Assignments"
                hits={grouped.assignment}
                onPick={go}
              />
              <ResultGroup title="OTPs" hits={grouped.otp} onPick={go} />
              <ResultGroup
                title="Students"
                hits={grouped.student}
                onPick={go}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ResultGroup({
  title,
  hits,
  onPick,
}: {
  title: string;
  hits: SearchHit[];
  onPick: (href: string) => void;
}) {
  if (hits.length === 0) return null;
  return (
    <div className="px-2 py-1">
      <div className="px-3 py-1 font-mono text-[9.5px] uppercase tracking-[0.2em] text-ink-40">
        {title}
      </div>
      {hits.map((h) => (
        <ResultRow key={h.key} hit={h} onPick={onPick} />
      ))}
    </div>
  );
}

function ResultRow({
  hit,
  onPick,
}: {
  hit: SearchHit;
  onPick: (href: string) => void;
}) {
  function handle(e: ReactMouseEvent<HTMLButtonElement>) {
    e.preventDefault();
    onPick(hit.href);
  }
  return (
    <button
      type="button"
      onClick={handle}
      className="block w-full rounded-md px-3 py-2 text-left transition hover:bg-[rgba(34,211,238,0.08)]"
    >
      <div className="font-sans text-[13px] text-ink-100">{hit.label}</div>
      <div className="font-mono text-[10.5px] text-ink-40">{hit.sub}</div>
    </button>
  );
}
