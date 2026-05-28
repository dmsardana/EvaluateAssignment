"use client";

import { useEffect, useState } from "react";

import { api, ReportViewsResponse } from "@/lib/api";
import { Matrix } from "./matrix";

export default function ReportViewsPage() {
  const [data, setData] = useState<ReportViewsResponse | null>(null);
  const [draft, setDraft] = useState<Record<string, string[]> | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function reload() {
    try {
      const r = await api.reportViews();
      setData(r);
      setDraft(r.by_tier);
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }

  useEffect(() => {
    void reload();
  }, []);

  if (!data || !draft) {
    return <div className="p-6 text-ink-60">{error ?? "Loading…"}</div>;
  }

  const dirty = JSON.stringify(draft) !== JSON.stringify(data.by_tier);

  async function save() {
    if (!draft) return;
    setSaving(true);
    try {
      const r = await api.setReportViews({ by_tier: draft });
      setData(r);
      setDraft(r.by_tier);
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  async function resetTier(tier: string) {
    try {
      const r = await api.resetReportViews(tier);
      setData(r);
      setDraft(r.by_tier);
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <div className="p-6 space-y-4">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Report Components</h1>
          <p className="text-sm text-ink-50">
            Configure which sections appear in the PDF report, per tier.
            Locked rows always render.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            disabled={!dirty}
            onClick={() => setDraft(data.by_tier)}
            className="px-3 py-1 border border-ink-10 rounded disabled:opacity-40"
          >
            Discard
          </button>
          <button
            disabled={!dirty || saving}
            onClick={save}
            className="px-3 py-1 rounded bg-sky-600 text-white disabled:opacity-40"
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </header>
      {error ? <div className="text-red-400 text-sm">{error}</div> : null}
      <Matrix
        catalog={data.catalog}
        tiers={data.tiers}
        draft={draft}
        onChange={setDraft}
        onResetTier={resetTier}
      />
    </div>
  );
}
