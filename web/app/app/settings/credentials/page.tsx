"use client";

import { useState } from "react";

import { CredentialCard } from "@/components/credentials-cards";
import {
  CredentialStatus,
  updateAnthropicKey,
  updateGeminiKey,
  updateOpenaiKey,
  useCredentials,
} from "@/lib/credentials";

// Credentials that have their own key-update form below — we hide
// their generic status card to avoid duplicate sections. Their status
// chip is rendered inline by ProviderKeyForm.
const FORMED_CREDS = new Set(["anthropic_api", "gemini_api", "openai_api"]);

export default function CredentialsPage() {
  const { data, refresh } = useCredentials();

  function statusOf(name: string): CredentialStatus | undefined {
    return data?.find((c) => c.name === name)?.status;
  }

  return (
    <div className="space-y-6 p-6">
      <header>
        <h1 className="text-2xl font-semibold text-ink-100">Credentials</h1>
        <p className="mt-1 text-sm text-ink-40">
          External APIs the pipeline depends on. Status is checked every 15 minutes.
        </p>
      </header>

      <div className="space-y-3">
        {data
          ?.filter((c) => !FORMED_CREDS.has(c.name))
          .map((c) => (
            <CredentialCard key={c.name} cred={c} onRefresh={refresh} />
          ))}
      </div>

      <ProviderKeyForm
        title="Anthropic API key"
        envVar="ANTHROPIC_API_KEY"
        placeholder="sk-ant-…"
        onSave={updateAnthropicKey}
        onSaved={refresh}
        currentStatus={statusOf("anthropic_api")}
      />

      <ProviderKeyForm
        title="Gemini API key"
        envVar="GEMINI_API_KEY"
        placeholder="AIza…"
        onSave={updateGeminiKey}
        onSaved={refresh}
        currentStatus={statusOf("gemini_api")}
        secondary
      />

      <ProviderKeyForm
        title="OpenAI API key"
        envVar="OPENAI_API_KEY"
        placeholder="sk-…"
        onSave={updateOpenaiKey}
        onSaved={refresh}
        currentStatus={statusOf("openai_api")}
        secondary
      />
    </div>
  );
}

function ProviderKeyForm({
  title,
  envVar,
  placeholder,
  onSave,
  onSaved,
  currentStatus,
  secondary,
}: {
  title: string;
  envVar: string;
  placeholder: string;
  onSave: (key: string) => Promise<void>;
  onSaved: () => void;
  currentStatus?: CredentialStatus;
  secondary?: boolean;
}) {
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  async function handle() {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      await onSave(draft.trim());
      setDraft("");
      setSaved(true);
      onSaved();
    } catch (e: unknown) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="rounded-md border border-ink-10 bg-ink-5 p-4">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-medium text-ink-100">Update {title}</h2>
        {currentStatus && <StatusChip status={currentStatus} />}
      </div>
      <p className="mt-1 text-xs text-ink-40">
        Validated against the provider before being written to{" "}
        <span className="font-mono">.env</span> as{" "}
        <span className="font-mono">{envVar}</span>. Invalid keys are rejected.
      </p>
      <div className="mt-3 flex gap-2">
        <input
          type="password"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={placeholder}
          autoComplete="off"
          className="flex-1 rounded border border-ink-10 bg-ink-5 px-2 py-1 text-sm text-ink-100 outline-none focus:border-ink-40"
        />
        <button
          type="button"
          disabled={saving || !draft.trim()}
          onClick={handle}
          className={
            secondary
              ? "rounded border border-ink-10 bg-ink-10 px-3 py-1 text-sm text-ink-100 hover:bg-ink-20 disabled:opacity-50"
              : "rounded bg-[rgba(190,242,100,0.12)] px-3 py-1 text-sm text-ink-100 ring-1 ring-[rgba(190,242,100,0.4)] hover:bg-[rgba(190,242,100,0.18)] disabled:opacity-50"
          }
        >
          {saving ? "Validating…" : "Validate & save"}
        </button>
      </div>
      {error && <div className="mt-2 text-xs text-[var(--ts-red)]">{error}</div>}
      {saved && <div className="mt-2 text-xs text-[var(--lime)]">Saved.</div>}
    </section>
  );
}

function StatusChip({ status }: { status: CredentialStatus }) {
  const tone =
    status === "OK"
      ? "border-[rgba(190,242,100,0.4)] bg-[rgba(190,242,100,0.12)] text-[var(--lime)]"
      : status === "MISSING"
        ? "border-ink-10 bg-ink-5 text-ink-40"
        : "border-[rgba(248,113,113,0.4)] bg-[rgba(248,113,113,0.12)] text-[var(--ts-red)]";
  return (
    <span
      className={`rounded-md border px-2 py-[2px] font-mono text-[10px] uppercase tracking-[0.18em] ${tone}`}
    >
      {status}
    </span>
  );
}
