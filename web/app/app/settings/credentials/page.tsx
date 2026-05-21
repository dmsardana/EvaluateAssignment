"use client";

import { useState } from "react";

import { CredentialCard } from "@/components/credentials-cards";
import {
  updateAnthropicKey,
  updateGeminiKey,
  updateOpenaiKey,
  useCredentials,
} from "@/lib/credentials";

export default function CredentialsPage() {
  const { data, refresh } = useCredentials();

  return (
    <div className="space-y-6 p-6">
      <header>
        <h1 className="text-2xl font-semibold text-ink-100">Credentials</h1>
        <p className="mt-1 text-sm text-ink-40">
          External APIs the pipeline depends on. Status is checked every 15 minutes.
        </p>
      </header>

      <div className="space-y-3">
        {data?.map((c) => (
          <CredentialCard key={c.name} cred={c} onRefresh={refresh} />
        ))}
      </div>

      <ProviderKeyForm
        title="Anthropic API key"
        envVar="ANTHROPIC_API_KEY"
        placeholder="sk-ant-…"
        onSave={updateAnthropicKey}
        onSaved={refresh}
      />

      <ProviderKeyForm
        title="Gemini API key"
        envVar="GEMINI_API_KEY"
        placeholder="AIza…"
        onSave={updateGeminiKey}
        onSaved={refresh}
        secondary
      />

      <ProviderKeyForm
        title="OpenAI API key"
        envVar="OPENAI_API_KEY"
        placeholder="sk-…"
        onSave={updateOpenaiKey}
        onSaved={refresh}
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
  secondary,
}: {
  title: string;
  envVar: string;
  placeholder: string;
  onSave: (key: string) => Promise<void>;
  onSaved: () => void;
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
      <h2 className="text-sm font-medium text-ink-100">Update {title}</h2>
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
