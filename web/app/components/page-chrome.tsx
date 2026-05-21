/**
 * Page chrome shared by every console route — editorial header with
 * mono eyebrow + display-serif headline + optional right-side actions.
 */
export function PageHeader({
  eyebrow,
  title,
  lede,
  actions,
}: {
  eyebrow: string;
  title: React.ReactNode;
  lede?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <header className="flex flex-col gap-6 border-b border-ink-10 px-6 py-10 md:flex-row md:items-end md:justify-between md:px-10 md:py-12">
      <div className="max-w-3xl">
        <div className="font-mono text-[10.5px] uppercase tracking-[0.24em] text-ink-40">
          {eyebrow}
        </div>
        <h1 className="mt-3 font-display text-[40px] font-semibold leading-[1.02] tracking-[-0.015em] text-ink-100 md:text-[52px]">
          {title}
        </h1>
        {lede && (
          <p className="mt-3 max-w-xl text-[14px] leading-relaxed text-ink-80">
            {lede}
          </p>
        )}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  );
}

export function EmptyState({
  title,
  hint,
  icon,
}: {
  title: string;
  hint?: string;
  icon?: React.ReactNode;
}) {
  return (
    <div className="mx-6 my-12 flex flex-col items-center justify-center rounded-2xl border border-dashed border-ink-10 bg-[rgba(24,24,27,0.45)] px-10 py-16 text-center md:mx-10">
      {icon && <div className="mb-4 text-ink-40">{icon}</div>}
      <div className="font-display text-[26px] text-ink-100">{title}</div>
      {hint && (
        <div className="mt-2 max-w-md text-[13px] text-ink-40">{hint}</div>
      )}
    </div>
  );
}

export function ErrorState({ error }: { error: unknown }) {
  const msg = error instanceof Error ? error.message : String(error);
  return (
    <div className="mx-6 my-12 rounded-2xl border border-[rgba(248,113,113,0.4)] bg-[rgba(248,113,113,0.08)] px-6 py-5 md:mx-10">
      <div className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-[var(--ts-red)]">
        backend error
      </div>
      <div className="mt-2 font-display text-[18px] text-ink-100">
        Couldn&apos;t reach this endpoint.
      </div>
      <div className="mt-2 font-mono text-[12px] text-ink-80">{msg}</div>
    </div>
  );
}

export function LoadingState({ label = "loading" }: { label?: string }) {
  return (
    <div className="mx-6 my-12 flex items-center gap-3 text-ink-40 md:mx-10">
      <span
        aria-hidden
        className="inline-block h-2 w-2 animate-pulse rounded-full"
        style={{ background: "var(--cyan)", boxShadow: "0 0 8px var(--cyan)" }}
      />
      <span className="font-mono text-[11px] uppercase tracking-[0.22em]">
        {label}…
      </span>
    </div>
  );
}

export const QUEUE_STATUS_STYLE: Record<
  string,
  { border: string; bg: string; fg: string }
> = {
  DETECTED: {
    border: "border-ink-10",
    bg: "bg-ink-5",
    fg: "text-ink-40",
  },
  GENERATING: {
    border: "border-[rgba(34,211,238,0.4)]",
    bg: "bg-[rgba(34,211,238,0.1)]",
    fg: "text-[var(--cyan)]",
  },
  PENDING_REVIEW: {
    border: "border-[rgba(236,72,153,0.4)]",
    bg: "bg-[rgba(236,72,153,0.1)]",
    fg: "text-[var(--magenta)]",
  },
  NEEDS_REGEN: {
    border: "border-[rgba(248,113,113,0.4)]",
    bg: "bg-[rgba(248,113,113,0.1)]",
    fg: "text-[var(--ts-red)]",
  },
  APPROVED: {
    border: "border-[rgba(190,242,100,0.4)]",
    bg: "bg-[rgba(190,242,100,0.1)]",
    fg: "text-[var(--lime)]",
  },
  SHARED: {
    border: "border-[rgba(139,92,246,0.4)]",
    bg: "bg-[rgba(139,92,246,0.1)]",
    fg: "text-[var(--violet)]",
  },
};

export function StatusPill({ status }: { status: string }) {
  const s = QUEUE_STATUS_STYLE[status] ?? QUEUE_STATUS_STYLE.DETECTED;
  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-[3px] font-mono text-[10px] font-medium uppercase tracking-[0.14em] ${s.border} ${s.bg} ${s.fg}`}
    >
      {status.replace(/_/g, " ")}
    </span>
  );
}

export function TypePill({ type }: { type: string }) {
  return (
    <span className="inline-flex items-center rounded-md border border-ink-10 bg-ink-5 px-2 py-[3px] font-mono text-[10px] font-semibold tracking-[0.14em] text-ink-100">
      {type}
    </span>
  );
}

export const BAND_STYLE: Record<string, { fg: string; label: string }> = {
  TRBLZ: { fg: "text-[var(--lime)]", label: "Trailblazer" },
  QUALIF: { fg: "text-[var(--cyan)]", label: "Qualifier" },
  DEVLP: { fg: "text-[var(--magenta)]", label: "Developing" },
  "F-GAPS": { fg: "text-[var(--ts-red)]", label: "Foundational Gaps" },
};

export function BandPill({ band }: { band: string }) {
  const s = BAND_STYLE[band] ?? { fg: "text-ink-40", label: band };
  return (
    <span
      className={`inline-flex items-center rounded-md border border-ink-10 bg-ink-5 px-2 py-[3px] font-mono text-[10px] font-medium uppercase tracking-[0.14em] ${s.fg}`}
    >
      {s.label}
    </span>
  );
}
