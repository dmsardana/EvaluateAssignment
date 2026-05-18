"use client";

import Image from "next/image";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";

import { PipelinePill } from "./pipeline-pill";
import { UserMenu } from "./user-menu";

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
          <Image
            src="/brand/mark.png"
            alt="thinkingSouls mark"
            width={44}
            height={44}
            className="h-10 w-10 object-contain"
            priority
          />
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

      <div className="relative hidden max-w-[520px] sm:block">
        <input
          type="text"
          placeholder="Search students, assignments, OTPs…"
          className="w-full rounded-[10px] border border-ink-10 bg-ink-5 px-4 py-[11px] pl-10 font-sans text-[13px] text-ink-100 outline-none transition focus:border-cyan focus:shadow-[0_0_0_3px_rgba(34,211,238,0.15)]"
        />
        <div
          className="pointer-events-none absolute left-[14px] top-1/2 h-[14px] w-[14px] -translate-y-1/2 rounded-full border-[1.5px] border-ink-40"
          aria-hidden
        />
        <span className="absolute right-[10px] top-1/2 -translate-y-1/2 rounded-[5px] border border-ink-10 bg-ink-10 px-[7px] py-[3px] font-mono text-[10px] text-ink-40">
          ⌘ K
        </span>
      </div>

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
        <button className="hidden rounded-lg border border-ink-10 bg-ink-5 px-[14px] py-[9px] font-sans text-[12px] font-medium text-ink-80 hover:bg-ink-10 hover:text-ink-100 md:inline-flex">
          ⌘P · Command
        </button>
      </div>

      <UserMenu />
    </header>
  );
}
