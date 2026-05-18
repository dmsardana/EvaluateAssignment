"use client";

import { useState } from "react";
import { CredentialCard } from "@/components/credentials-cards";
import { useCredentials, updateAnthropicKey } from "@/lib/credentials";

export default function CredentialsPage() {
  const { data, refresh } = useCredentials();
  const [draftKey, setDraftKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  async function handleSave() {
    setSaving(true);
    setSaveError(null);
    setSaved(false);
    try {
      await updateAnthropicKey(draftKey.trim());
      setDraftKey("");
      setSaved(true);
      refresh();
    } catch (e: unknown) {
      setSaveError((e as Error).message);
    } finally {
      setSaving(false);
    }
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
        {data?.map((c) => (
          <CredentialCard key={c.name} cred={c} onRefresh={refresh} />
        ))}
      </div>

      <section className="rounded-md border border-ink-10 bg-ink-5 p-4">
        <h2 className="text-sm font-medium text-ink-100">Update Anthropic API key</h2>
        <p className="mt-1 text-xs text-ink-40">
          The key is validated against Anthropic before being written to .env. Invalid keys are rejected.
        </p>
        <div className="mt-3 flex gap-2">
          <input
            type="password"
            value={draftKey}
            onChange={(e) => setDraftKey(e.target.value)}
            placeholder="sk-ant-…"
            className="flex-1 rounded border border-ink-10 bg-ink-5 px-2 py-1 text-sm text-ink-100 outline-none focus:border-ink-40"
          />
          <button
            type="button"
            disabled={saving || !draftKey.trim()}
            onClick={handleSave}
            className="rounded bg-[rgba(190,242,100,0.12)] px-3 py-1 text-sm text-ink-100 ring-1 ring-[rgba(190,242,100,0.4)] hover:bg-[rgba(190,242,100,0.18)] disabled:opacity-50"
          >
            {saving ? "Validating…" : "Validate & save"}
          </button>
        </div>
        {saveError && <div className="mt-2 text-xs text-[var(--ts-red)]">{saveError}</div>}
        {saved && <div className="mt-2 text-xs text-[var(--lime)]">Saved.</div>}
      </section>
    </div>
  );
}
