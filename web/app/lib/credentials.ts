// web/app/lib/credentials.ts
import useSWR from "swr";
import { useEffect } from "react";

export type CredentialStatus =
  | "OK"
  | "EXPIRED"
  | "REVOKED"
  | "MISSING"
  | "UNKNOWN";

export interface CredentialHealth {
  name: string;
  status: CredentialStatus;
  last_checked_at: string | null;
  last_ok_at: string | null;
  last_error: string | null;
  recovery_started_at: string | null;
  notified_at: string | null;
  updated_at: string | null;
}

const fetcher = (url: string) =>
  fetch(url, { credentials: "include" }).then((r) => {
    if (!r.ok) throw new Error(`status ${r.status}`);
    return r.json() as Promise<CredentialHealth[]>;
  });

export function useCredentials() {
  const { data, error, mutate } = useSWR<CredentialHealth[]>(
    "/api/credentials/status",
    fetcher,
    { refreshInterval: 30_000 },
  );
  const issues = (data ?? []).filter((c) => c.status !== "OK");
  return {
    data,
    error,
    issues,
    isLoading: !data && !error,
    refresh: mutate,
  };
}

export async function startGoogleReauth(): Promise<{ consent_url: string; state: string }> {
  const r = await fetch("/api/credentials/google_oauth/reauth", {
    method: "POST",
    credentials: "include",
  });
  if (!r.ok) throw new Error(`reauth failed: ${r.status}`);
  return r.json();
}

export async function updateAnthropicKey(apiKey: string): Promise<void> {
  return updateProviderKey("anthropic_api", apiKey);
}

export async function updateGeminiKey(apiKey: string): Promise<void> {
  return updateProviderKey("gemini_api", apiKey);
}

export async function updateOpenaiKey(apiKey: string): Promise<void> {
  return updateProviderKey("openai_api", apiKey);
}

// Generic provider-key update. Backend routes follow the
// `/api/credentials/<name>/update` convention; the handle validates
// the key via a live probe before persisting it to .env.
async function updateProviderKey(name: string, apiKey: string): Promise<void> {
  const r = await fetch(`/api/credentials/${name}/update`, {
    method: "POST",
    credentials: "include",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ api_key: apiKey }),
  });
  if (!r.ok) {
    const body = await r.json().catch(() => ({ detail: "unknown" }));
    throw new Error(body.detail || `status ${r.status}`);
  }
}

export async function recheckCredential(name: string): Promise<void> {
  const r = await fetch(`/api/credentials/${name}/recheck`, {
    method: "POST",
    credentials: "include",
  });
  if (!r.ok) throw new Error(`recheck failed: ${r.status}`);
}

export function useWatchReauthCompletion(refresh: () => void) {
  useEffect(() => {
    function onStorage(e: StorageEvent) {
      if (e.key === "ts:google_reconnected") refresh();
    }
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [refresh]);
}
