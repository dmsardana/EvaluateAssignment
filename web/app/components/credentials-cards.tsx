"use client";

import { useState } from "react";

import {
  CredentialHealth,
  recheckCredential,
  startGoogleReauth,
} from "@/lib/credentials";

const STATUS_TONE: Record<CredentialHealth["status"], string> = {
  OK: "text-[var(--lime)]",
  EXPIRED: "text-amber-300",
  REVOKED: "text-[var(--ts-red)]",
  MISSING: "text-[var(--ts-red)]",
  UNKNOWN: "text-ink-40",
};

export function CredentialCard({
  cred,
  onRefresh,
}: {
  cred: CredentialHealth;
  onRefresh: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const lastChecked = cred.last_checked_at
    ? new Date(cred.last_checked_at).toLocaleString()
    : "never";
  const isGoogle = cred.name === "google_oauth";

  async function handleRecheck() {
    setBusy(true);
    setError(null);
    try {
      await recheckCredential(cred.name);
      onRefresh();
    } catch (e: unknown) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleReconnect() {
    setBusy(true);
    setError(null);
    try {
      const { consent_url } = await startGoogleReauth();
      window.open(consent_url, "_blank", "noopener,noreferrer");
    } catch (e: unknown) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-md border border-ink-10 bg-ink-5 p-3 text-sm">
      <div className="flex items-baseline justify-between">
        <div className="font-medium text-ink-100">
          {isGoogle ? "Google (OAuth)" : "Anthropic API"}
        </div>
        <div className={`font-mono text-xs ${STATUS_TONE[cred.status]}`}>
          {cred.status}
        </div>
      </div>
      <div className="mt-1 text-xs text-ink-40">last check: {lastChecked}</div>
      {cred.last_error && (
        <div className="mt-2 line-clamp-2 text-xs text-[var(--ts-red)]/80">
          {cred.last_error}
        </div>
      )}
      <div className="mt-3 flex gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={handleRecheck}
          className="rounded border border-ink-10 px-2 py-1 text-xs text-ink-80 hover:bg-ink-10 hover:text-ink-100 disabled:opacity-50"
        >
          {busy ? "…" : "Test now"}
        </button>
        {isGoogle && cred.status !== "OK" && (
          <button
            type="button"
            disabled={busy}
            onClick={handleReconnect}
            className="rounded bg-[rgba(248,113,113,0.12)] px-2 py-1 text-xs text-ink-100 ring-1 ring-[rgba(248,113,113,0.4)] hover:bg-[rgba(248,113,113,0.18)] disabled:opacity-50"
          >
            Reconnect Google →
          </button>
        )}
      </div>
      {error && (
        <div className="mt-2 text-xs text-[var(--ts-red)]">{error}</div>
      )}
    </div>
  );
}
