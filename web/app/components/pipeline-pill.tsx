"use client";

import * as Popover from "@radix-ui/react-popover";

import { useCredentials } from "@/lib/credentials";

type Tone = "ok" | "warn" | "broken" | "unknown";

// Map abstract tones to the existing design system.
// ok      → green (matches the original Pipeline · live dot)
// warn    → magenta with pulse (matches the existing "awaiting approval" alert chip)
// broken  → red, hard pulse
// unknown → neutral ink
const TONE_DOT_STYLE: Record<Tone, React.CSSProperties> = {
  ok: { background: "var(--lime)", boxShadow: "0 0 6px var(--lime)" },
  warn: {
    background: "var(--magenta)",
    boxShadow: "0 0 8px var(--magenta), 0 0 14px rgba(236,72,153,0.45)",
  },
  broken: {
    background: "var(--ts-red)",
    boxShadow: "0 0 8px var(--ts-red), 0 0 14px rgba(248,113,113,0.55)",
  },
  unknown: { background: "var(--ink-40, #6b7280)", boxShadow: "none" },
};

const TONE_PILL_CLASS: Record<Tone, string> = {
  ok: "border-ink-10 bg-ink-5 text-ink-80 hover:bg-ink-10 hover:text-ink-100",
  warn: "border-[rgba(236,72,153,0.4)] bg-[linear-gradient(135deg,rgba(236,72,153,0.18),rgba(139,92,246,0.18))] text-ink-100 hover:brightness-110",
  broken:
    "border-[rgba(248,113,113,0.4)] bg-[rgba(248,113,113,0.12)] text-ink-100 hover:bg-[rgba(248,113,113,0.18)] animate-pulse",
  unknown: "border-ink-10 bg-ink-5 text-ink-40",
};

export function PipelinePill() {
  const { issues, isLoading, error } = useCredentials();

  let label = "Pipeline · live";
  let tone: Tone = "ok";

  if (error || isLoading) {
    label = "Credentials · …";
    tone = "unknown";
  } else if (issues.length > 0) {
    const noun = issues.length === 1 ? "issue" : "issues";
    label = `Credentials · ${issues.length} ${noun}`;
    tone = issues.some(
      (i) => i.status === "REVOKED" || i.status === "MISSING",
    )
      ? "broken"
      : "warn";
  }

  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <button
          type="button"
          className={`hidden items-center gap-[6px] rounded-lg border px-[14px] py-[9px] font-sans text-[12px] font-medium transition md:inline-flex ${TONE_PILL_CLASS[tone]}`}
        >
          <span
            className="h-[6px] w-[6px] rounded-full"
            style={TONE_DOT_STYLE[tone]}
            aria-hidden
          />
          {label}
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="end"
          sideOffset={8}
          className="z-50 w-96 rounded-lg border border-ink-10 bg-ink-5 p-3 text-ink-100 shadow-xl"
        >
          {/* Task 5.3 will replace this placeholder with <CredentialsPopover /> */}
          <div className="text-xs text-ink-60">
            Credentials panel — landing in next commit.
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
