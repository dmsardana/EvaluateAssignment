import Link from "next/link";

import { CredentialsPopover } from "@/components/credentials-popover";
import { PipelinePill } from "@/components/pipeline-pill";

export default function WelcomePage() {
  return (
    <div className="relative mx-auto flex min-h-screen max-w-6xl flex-col px-6 py-10 md:px-12 md:py-16">
      <div className="absolute right-6 top-10 md:right-12 md:top-16">
        <PipelinePill />
      </div>

      <header className="max-w-3xl">
        <div className="flex items-center gap-3 font-mono text-[10.5px] uppercase tracking-[0.24em] text-ink-40">
          <span
            aria-hidden
            className="inline-block h-[6px] w-[6px] rounded-full"
            style={{ background: "var(--lime)", boxShadow: "0 0 8px var(--lime)" }}
          />
          Evaluation Console · Welcome
        </div>
        <h1 className="mt-6 font-display text-[56px] font-semibold leading-[0.98] tracking-[-0.02em] text-ink-100 md:text-[80px]">
          The pipeline
          <br />
          is{" "}
          <span
            className="relative italic"
            style={{ color: "var(--ts-red)", textShadow: "0 0 32px var(--ts-red-glow)" }}
          >
            live
          </span>
          .
        </h1>
        <p className="mt-6 max-w-xl text-[15px] leading-relaxed text-ink-80">
          Credentials are re-checked every 15 minutes. The pill in the top-right
          turns red when anything breaks. Jump into the queue or wander the
          menu — everything here reads live from the backend.
        </p>
      </header>

      <section className="mt-14 grid gap-10 md:grid-cols-[1fr_auto] md:items-start">
        <div className="rounded-2xl border border-ink-10 bg-[rgba(24,24,27,0.6)] p-6">
          <div className="mb-4 flex items-baseline justify-between">
            <h2 className="font-display text-[22px] font-medium text-ink-100">
              Credential health
            </h2>
            <span className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-ink-40">
              auto-refresh · 30s
            </span>
          </div>
          <CredentialsPopover />
        </div>

        <nav className="space-y-3">
          <Link
            href="/"
            className="block rounded-xl border border-ink-10 bg-[rgba(24,24,27,0.45)] px-5 py-4 transition hover:border-[rgba(248,113,113,0.4)] hover:bg-[rgba(248,113,113,0.06)]"
          >
            <div className="font-display text-[17px] text-ink-100">
              Approval queue →
            </div>
            <div className="mt-1 font-mono text-[10.5px] uppercase tracking-[0.2em] text-ink-40">
              what needs your attention
            </div>
          </Link>
          <Link
            href="/settings/credentials"
            className="block rounded-xl border border-ink-10 bg-[rgba(24,24,27,0.45)] px-5 py-4 transition hover:border-[rgba(248,113,113,0.4)] hover:bg-[rgba(248,113,113,0.06)]"
          >
            <div className="font-display text-[17px] text-ink-100">
              Manage credentials →
            </div>
            <div className="mt-1 font-mono text-[10.5px] uppercase tracking-[0.2em] text-ink-40">
              Anthropic key, reconnect Google
            </div>
          </Link>
        </nav>
      </section>
    </div>
  );
}
