"use client";

import Link from "next/link";
import useSWR from "swr";

import {
  ErrorState,
  LoadingState,
  PageHeader,
} from "@/components/page-chrome";
import { api, DistributionResponse, StatsResponse } from "@/lib/api";

export default function WorkspacePage() {
  const stats = useSWR<StatsResponse>("/api/stats", () => api.stats());
  const dist = useSWR<DistributionResponse>("/api/distribution", () =>
    api.distribution(),
  );

  const isLoading = stats.isLoading || dist.isLoading;
  const firstError = stats.error || dist.error;

  return (
    <div>
      <PageHeader
        eyebrow="Settings · Workspace"
        title="The shop."
        lede="A snapshot of the pipeline this week. Detailed knobs live in the .env file and Credentials settings."
      />

      {isLoading && <LoadingState label="loading workspace" />}
      {firstError && <ErrorState error={firstError} />}

      {stats.data && (
        <section className="grid gap-3 px-6 pt-8 sm:grid-cols-3 md:px-10">
          <Stat
            label="Awaiting keys"
            value={stats.data.awaiting_keys}
            tone={stats.data.awaiting_keys > 0 ? "magenta" : "ink"}
          />
          <Stat
            label="Submissions queued"
            value={stats.data.submissions_queued}
          />
          <Stat
            label="Est. cost this week"
            value={`$${stats.data.estimated_cost_usd.toFixed(2)}`}
          />
        </section>
      )}

      {dist.data && (
        <section className="px-6 py-8 md:px-10">
          <h2 className="font-display text-[22px] text-ink-100">
            This week — {dist.data.week_label}
          </h2>
          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <BandStat
              label="Trailblazer"
              n={dist.data.trailblazer}
              tone="var(--lime)"
            />
            <BandStat
              label="Qualifier"
              n={dist.data.qualifier}
              tone="var(--cyan)"
            />
            <BandStat
              label="Developing"
              n={dist.data.developing}
              tone="var(--magenta)"
            />
            <BandStat
              label="Foundational Gaps"
              n={dist.data.foundational_gaps}
              tone="var(--ts-red)"
            />
          </div>
          <div className="mt-3 font-mono text-[11px] text-ink-40">
            {dist.data.total} total · evaluated this week
          </div>
        </section>
      )}

      <section className="border-t border-ink-10 px-6 py-10 md:px-10">
        <h2 className="font-display text-[22px] text-ink-100">Knobs</h2>
        <p className="mt-1 max-w-2xl text-[13px] text-ink-80">
          Most pipeline behaviour is configured in the project root{" "}
          <code className="font-mono text-ink-100">.env</code> file. Restart{" "}
          <code className="font-mono text-ink-100">scripts/start-api.sh</code>{" "}
          after edits.
        </p>
        <ul className="mt-4 grid gap-2 text-[13px] sm:grid-cols-2">
          <KnobCard
            name="ANTHROPIC_API_KEY"
            blurb="Anthropic Claude key. Validate + rotate from /settings/credentials."
          />
          <KnobCard
            name="CUTOFF_DATE"
            blurb="Ignore Classroom submissions before this date."
          />
          <KnobCard
            name="OPS_ALERT_EMAIL"
            blurb="Where credential-broken emails are sent."
          />
          <KnobCard
            name="GOOGLE_TOKEN_PATH"
            blurb="Where the Google OAuth refresh token is cached."
          />
        </ul>
        <div className="mt-6">
          <Link
            href="/settings/credentials"
            className="font-mono text-[11px] uppercase tracking-[0.2em] text-[var(--cyan)] hover:text-ink-100"
          >
            Manage credentials →
          </Link>
        </div>
      </section>
    </div>
  );
}

function Stat({
  label,
  value,
  tone = "ink",
}: {
  label: string;
  value: number | string;
  tone?: "ink" | "magenta";
}) {
  return (
    <div
      className={`rounded-xl border p-4 ${
        tone === "magenta"
          ? "border-[rgba(236,72,153,0.4)] bg-[rgba(236,72,153,0.06)]"
          : "border-ink-10 bg-[rgba(24,24,27,0.55)]"
      }`}
    >
      <div className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-ink-40">
        {label}
      </div>
      <div className="mt-1 font-display text-[36px] tabular-nums text-ink-100">
        {value}
      </div>
    </div>
  );
}

function BandStat({
  label,
  n,
  tone,
}: {
  label: string;
  n: number;
  tone: string;
}) {
  return (
    <div className="rounded-xl border border-ink-10 bg-[rgba(24,24,27,0.55)] p-4">
      <div
        className="font-mono text-[10.5px] uppercase tracking-[0.18em]"
        style={{ color: tone }}
      >
        {label}
      </div>
      <div className="mt-1 font-display text-[28px] tabular-nums text-ink-100">
        {n}
      </div>
    </div>
  );
}

function KnobCard({ name, blurb }: { name: string; blurb: string }) {
  return (
    <li className="rounded-lg border border-ink-10 bg-[rgba(24,24,27,0.45)] p-3">
      <code className="font-mono text-[11.5px] text-ink-100">{name}</code>
      <p className="mt-1 text-[12px] text-ink-40">{blurb}</p>
    </li>
  );
}
