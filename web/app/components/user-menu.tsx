"use client";

/**
 * Auth-free stub. Scope B runs without next-auth on localhost — this
 * surface exists so top-bar.tsx can import it. When real auth lands,
 * swap this for a session-aware dropdown.
 */
export function UserMenu() {
  return (
    <div className="hidden items-center gap-2 rounded-lg border border-ink-10 bg-ink-5 px-3 py-2 md:flex">
      <div
        aria-hidden
        className="grid h-6 w-6 place-items-center rounded-full font-mono text-[10px] font-semibold text-ink-100"
        style={{
          background:
            "linear-gradient(135deg, var(--ts-red-soft), rgba(139,92,246,0.35))",
        }}
      >
        OP
      </div>
      <div className="leading-tight">
        <div className="font-sans text-[12px] font-medium text-ink-100">
          Operator
        </div>
        <div className="font-mono text-[9.5px] uppercase tracking-[0.18em] text-ink-40">
          local · no auth
        </div>
      </div>
    </div>
  );
}
