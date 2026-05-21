"use client";

import Link from "next/link";

import { PageHeader } from "@/components/page-chrome";
import { useCredentials } from "@/lib/credentials";

export default function SecurityPage() {
  const { data, issues, isLoading } = useCredentials();

  return (
    <div>
      <PageHeader
        eyebrow="Account · Security"
        title="Trust boundaries."
        lede="What the console can reach, what it doesn't store, and what's currently OK."
        actions={
          <Link
            href="/settings/credentials"
            className="rounded-md border border-ink-10 bg-ink-5 px-3 py-[6px] font-sans text-[12px] text-ink-100 hover:border-[rgba(34,211,238,0.4)]"
          >
            Manage credentials →
          </Link>
        }
      />

      <section className="px-6 py-8 md:px-10">
        <div className="rounded-xl border border-[rgba(248,113,113,0.4)] bg-[rgba(248,113,113,0.06)] p-5">
          <div className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-[var(--ts-red)]">
            heads up · localhost only
          </div>
          <p className="mt-2 max-w-2xl text-[13.5px] leading-relaxed text-ink-80">
            This console is currently auth-free. Anyone with network access to{" "}
            <code className="font-mono text-ink-100">localhost:3000</code> can
            reach every page. Keep it bound to{" "}
            <code className="font-mono text-ink-100">127.0.0.1</code> and
            don&apos;t port-forward it. Real login (next-auth) is on the roadmap.
          </p>
        </div>
      </section>

      <section className="px-6 pb-8 md:px-10">
        <h2 className="font-display text-[22px] text-ink-100">Live grants</h2>
        <p className="mt-1 max-w-2xl text-[13px] text-ink-80">
          External APIs the pipeline currently uses, with their last health
          status.
        </p>
        <ul className="mt-4 space-y-3">
          {isLoading && (
            <li className="font-mono text-[11px] text-ink-40">
              loading credentials…
            </li>
          )}
          {data?.map((c) => (
            <li
              key={c.name}
              className="flex flex-wrap items-baseline justify-between gap-3 rounded-xl border border-ink-10 bg-[rgba(24,24,27,0.5)] p-4"
            >
              <div>
                <div className="font-display text-[16px] text-ink-100">
                  {c.name === "google_oauth"
                    ? "Google OAuth"
                    : c.name === "anthropic_api"
                      ? "Anthropic API"
                      : c.name}
                </div>
                <div className="font-mono text-[11px] text-ink-40">
                  scopes:{" "}
                  {c.name === "google_oauth"
                    ? "Drive · Gmail · Classroom"
                    : c.name === "anthropic_api"
                      ? "messages (vision + text)"
                      : "—"}
                </div>
              </div>
              <span
                className={`font-mono text-[11px] uppercase tracking-[0.18em] ${
                  c.status === "OK"
                    ? "text-[var(--lime)]"
                    : "text-[var(--ts-red)]"
                }`}
              >
                {c.status}
              </span>
            </li>
          ))}
        </ul>
        {issues.length > 0 && (
          <p className="mt-3 font-mono text-[11px] text-[var(--ts-red)]">
            {issues.length} credential{issues.length === 1 ? "" : "s"} need
            attention — fix in Credentials.
          </p>
        )}
      </section>

      <section className="border-t border-ink-10 px-6 py-10 md:px-10">
        <h2 className="font-display text-[22px] text-ink-100">
          What the console stores
        </h2>
        <ul className="mt-4 grid gap-3 text-[13px] sm:grid-cols-2">
          <Boundary
            kind="kept"
            label="Token cache"
            blurb="token.json on disk (refresh token for Google) — gitignored."
          />
          <Boundary
            kind="kept"
            label="Credential health"
            blurb="Postgres credentials_health table — last_checked, last_error."
          />
          <Boundary
            kind="kept"
            label=".env"
            blurb="ANTHROPIC_API_KEY, OPS_ALERT_EMAIL, etc. Never committed."
          />
          <Boundary
            kind="never"
            label="Student PDFs"
            blurb="Pulled per evaluation, deleted after grading. Stays on Drive."
          />
          <Boundary
            kind="never"
            label="Anthropic messages"
            blurb="Sent to Anthropic for grading. Anthropic does not train on API requests."
          />
          <Boundary
            kind="never"
            label="Operator passwords"
            blurb="None — there's no login layer yet."
          />
        </ul>
      </section>
    </div>
  );
}

function Boundary({
  kind,
  label,
  blurb,
}: {
  kind: "kept" | "never";
  label: string;
  blurb: string;
}) {
  return (
    <li className="rounded-xl border border-ink-10 bg-[rgba(24,24,27,0.5)] p-4">
      <div className="flex items-baseline justify-between">
        <span className="font-display text-[16px] text-ink-100">{label}</span>
        <span
          className={`font-mono text-[10px] uppercase tracking-[0.18em] ${
            kind === "kept" ? "text-[var(--cyan)]" : "text-[var(--lime)]"
          }`}
        >
          {kind === "kept" ? "stored" : "not stored"}
        </span>
      </div>
      <p className="mt-1 text-[12px] text-ink-40">{blurb}</p>
    </li>
  );
}
