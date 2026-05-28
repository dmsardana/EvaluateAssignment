"use client";

import { useState } from "react";

import { startGoogleReauth, useCredentials } from "@/lib/credentials";

/**
 * Global banner shown across every page whenever the Google OAuth
 * credential is not OK. Sensitive scopes on an unverified production
 * app are capped by Google at a 7-day refresh-token lifetime, so this
 * pops up roughly weekly. Showing it prominently means operators see
 * the failure mode immediately instead of via a confusing 500 on
 * /api/queue.
 *
 * Two recovery paths:
 *  1. "Re-authenticate" button — opens the OAuth consent URL returned
 *     by /api/credentials/google_oauth/reauth in a new tab. After
 *     consent, the API server's status is updated and the banner
 *     clears on the next 30-second SWR refresh.
 *  2. CLI: ./scripts/reauth.sh — same flow but also restarts the API
 *     server. Useful when the API process itself is in a bad state.
 */
export function ReauthBanner() {
  const { data, isLoading, refresh } = useCredentials();
  const [launching, setLaunching] = useState(false);
  const [launchError, setLaunchError] = useState<string | null>(null);

  if (isLoading || !data) return null;
  const google = data.find((c) => c.name === "google_oauth");
  if (!google || google.status === "OK") return null;

  const statusLabel = google.status; // EXPIRED | REVOKED | MISSING | UNKNOWN
  const lastError = google.last_error || "Token unusable.";

  async function launchReauth() {
    setLaunching(true);
    setLaunchError(null);
    try {
      const { consent_url } = await startGoogleReauth();
      window.open(consent_url, "_blank", "noopener,noreferrer");
      // Re-check status shortly so the banner clears as soon as the
      // user finishes the consent flow in the other tab.
      setTimeout(() => refresh(), 8_000);
    } catch (e) {
      setLaunchError((e as Error).message);
    } finally {
      setLaunching(false);
    }
  }

  return (
    <div className="border-b border-[rgba(248,113,113,0.35)] bg-[rgba(248,113,113,0.10)] px-6 py-3 md:px-10">
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between md:gap-4">
        <div className="min-w-0">
          <div className="font-sans text-[13px] font-semibold text-[var(--ts-red)]">
            Google OAuth re-auth required ({statusLabel})
          </div>
          <div className="mt-0.5 truncate font-mono text-[11px] text-ink-60">
            {lastError}
          </div>
          <div className="mt-0.5 font-mono text-[10.5px] text-ink-40">
            Drive / Classroom / Gmail calls will fail until this is resolved.
            CLI alternative: <span className="text-ink-80">./scripts/reauth.sh</span>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            disabled={launching}
            onClick={launchReauth}
            className="rounded-md border border-[rgba(248,113,113,0.55)] bg-[rgba(248,113,113,0.18)] px-3 py-[6px] font-sans text-[12px] font-medium text-ink-100 transition hover:bg-[rgba(248,113,113,0.28)] disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {launching ? "Opening consent…" : "Re-authenticate"}
          </button>
        </div>
      </div>
      {launchError && (
        <div className="mt-2 font-mono text-[11px] text-[var(--ts-red)]">
          {launchError}
        </div>
      )}
    </div>
  );
}
