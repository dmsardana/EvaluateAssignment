"use client";

import useSWR from "swr";

import {
  ErrorState,
  LoadingState,
  PageHeader,
} from "@/components/page-chrome";
import { api, BudgetResponse, StatsResponse } from "@/lib/api";

interface BudgetShape {
  budget_usd: number;
  spent_usd: number;
  available_usd: number;
  cost_per_grading_usd: number;
}

function asBudget(b: BudgetResponse | undefined): BudgetShape | null {
  if (!b) return null;
  return {
    budget_usd: Number(b.budget_usd ?? 0),
    spent_usd: Number(b.spent_usd ?? 0),
    available_usd: Number(b.available_usd ?? 0),
    cost_per_grading_usd: Number(b.cost_per_grading_usd ?? 0),
  };
}

export default function BillingPage() {
  const budgetS = useSWR<BudgetResponse>("/api/budget", () => api.budget());
  const statsS = useSWR<StatsResponse>("/api/stats", () => api.stats());

  const isLoading = budgetS.isLoading || statsS.isLoading;
  const firstError = budgetS.error || statsS.error;
  const b = asBudget(budgetS.data);
  const burnPct =
    b && b.budget_usd > 0
      ? Math.min(100, Math.round((b.spent_usd / b.budget_usd) * 100))
      : 0;
  const burnTone =
    burnPct >= 90
      ? "var(--ts-red)"
      : burnPct >= 70
        ? "var(--magenta)"
        : "var(--lime)";

  return (
    <div>
      <PageHeader
        eyebrow="Settings · Billing"
        title="The meter."
        lede="What the pipeline is spending against the Anthropic budget. Set the cap in .env via ANTHROPIC_BUDGET_USD."
      />

      {isLoading && <LoadingState label="loading budget" />}
      {firstError && <ErrorState error={firstError} />}

      {b && (
        <section className="px-6 py-8 md:px-10">
          <div className="rounded-2xl border border-ink-10 bg-[rgba(24,24,27,0.55)] p-6">
            <div className="flex flex-wrap items-baseline justify-between gap-4">
              <div>
                <div className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-ink-40">
                  spent this cycle
                </div>
                <div className="mt-1 flex items-baseline gap-3">
                  <span className="font-display text-[48px] tabular-nums text-ink-100">
                    ${b.spent_usd.toFixed(2)}
                  </span>
                  <span className="font-mono text-[13px] text-ink-40">
                    of ${b.budget_usd.toFixed(2)}
                  </span>
                </div>
              </div>
              <div className="text-right">
                <div className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-ink-40">
                  available
                </div>
                <div className="mt-1 font-display text-[32px] tabular-nums text-[var(--lime)]">
                  ${b.available_usd.toFixed(2)}
                </div>
              </div>
            </div>
            <div className="mt-6 h-[6px] w-full overflow-hidden rounded-full bg-ink-10">
              <div
                className="h-full rounded-full transition-all"
                style={{
                  width: `${burnPct}%`,
                  background: burnTone,
                  boxShadow: `0 0 12px ${burnTone}`,
                }}
              />
            </div>
            <div className="mt-2 font-mono text-[11px] text-ink-40">
              {burnPct}% burned
            </div>
          </div>

          <div className="mt-6 grid gap-3 sm:grid-cols-3">
            <Card label="Cost per grading">
              ${b.cost_per_grading_usd.toFixed(2)}
            </Card>
            <Card label="This week (estimate)">
              ${statsS.data?.estimated_cost_usd.toFixed(2) ?? "0.00"}
            </Card>
            <Card label="Gradings affordable">
              <span className="tabular-nums">
                {b.cost_per_grading_usd > 0
                  ? Math.floor(b.available_usd / b.cost_per_grading_usd)
                  : "∞"}
              </span>
            </Card>
          </div>

          <div className="mt-8 rounded-xl border border-dashed border-ink-10 bg-[rgba(24,24,27,0.4)] p-5 text-[13px] text-ink-40">
            Budget enforcement happens server-side. To raise the cap, edit{" "}
            <code className="font-mono text-ink-80">.env</code>:{" "}
            <code className="font-mono text-ink-100">
              ANTHROPIC_BUDGET_USD=100
            </code>{" "}
            and restart the API.
          </div>
        </section>
      )}
    </div>
  );
}

function Card({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-ink-10 bg-[rgba(24,24,27,0.55)] p-4">
      <div className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-ink-40">
        {label}
      </div>
      <div className="mt-1 font-display text-[28px] text-ink-100">
        {children}
      </div>
    </div>
  );
}
