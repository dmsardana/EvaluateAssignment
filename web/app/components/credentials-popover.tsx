"use client";

import Link from "next/link";

import { useCredentials, useWatchReauthCompletion } from "@/lib/credentials";

import { CredentialCard } from "./credentials-cards";

export function CredentialsPopover() {
  const { data, isLoading, error, refresh } = useCredentials();
  useWatchReauthCompletion(refresh);

  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm font-medium text-ink-100">Credentials</h3>
        <Link
          href="/settings/credentials"
          className="text-xs text-ink-40 hover:text-ink-100"
        >
          Manage all →
        </Link>
      </div>
      {isLoading && <div className="text-xs text-ink-40">loading…</div>}
      {error && (
        <div className="text-xs text-[var(--ts-red)]">{String(error)}</div>
      )}
      {data &&
        data.map((c) => (
          <CredentialCard
            key={c.name}
            cred={c}
            onRefresh={() => refresh()}
          />
        ))}
    </div>
  );
}
