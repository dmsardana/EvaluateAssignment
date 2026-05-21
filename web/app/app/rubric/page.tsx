"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";

import {
  ErrorState,
  LoadingState,
  PageHeader,
} from "@/components/page-chrome";
import {
  api,
  RubricResponse,
  Thresholds,
  TierCutoffs,
} from "@/lib/api";

const TIER_DESCRIPTION: Record<keyof TierCutoffs, string> = {
  WA: "Worksheet — promotes to QA when threshold is met.",
  QA: "Quarterly — promotes to AA when threshold is met.",
  AA: "Annual — terminal tier (no promotion).",
  ZA: "Diagnostic — promotes to pass terminal when met.",
};

export default function RubricPage() {
  const rubricS = useSWR<RubricResponse>("/api/settings/rubric", () =>
    api.rubric(),
  );
  const thresholdsS = useSWR<Thresholds>("/api/settings/thresholds", () =>
    api.thresholds(),
  );
  const cutoffsS = useSWR<TierCutoffs>("/api/settings/tier-cutoffs", () =>
    api.tierCutoffs(),
  );

  const isLoading =
    rubricS.isLoading || thresholdsS.isLoading || cutoffsS.isLoading;
  const firstError = rubricS.error || thresholdsS.error || cutoffsS.error;

  return (
    <div>
      <PageHeader
        eyebrow="Configure · Rubric"
        title={
          <>
            Five dimensions.{" "}
            <span className="italic text-[var(--ts-red)]">One verdict.</span>
          </>
        }
        lede="Each question is scored 0–1 along five weighted dimensions. Aggregates roll up into performance bands."
      />

      {isLoading && <LoadingState label="loading rubric" />}
      {firstError && <ErrorState error={firstError} />}

      {rubricS.data && (
        <section className="px-6 py-10 md:px-10">
          <h2 className="font-display text-[26px] text-ink-100">Dimensions</h2>
          <p className="mt-1 max-w-2xl text-[13px] text-ink-80">
            Weights sum to 1.00. Per-question score is the weighted sum, capped at
            1.00. Weights are locked by the pipeline — change them in code only.
          </p>
          <div className="mt-6 grid gap-4 lg:grid-cols-2">
            {rubricS.data.dimensions.map((d) => (
              <article
                key={d.key}
                className="rounded-xl border border-ink-10 bg-[rgba(24,24,27,0.55)] p-5"
              >
                <div className="flex items-baseline justify-between">
                  <h3 className="font-display text-[20px] text-ink-100">
                    {d.name}
                  </h3>
                  <span
                    className="font-mono text-[14px] tabular-nums"
                    style={{ color: "var(--lime)" }}
                  >
                    × {d.weight.toFixed(2)}
                  </span>
                </div>
                <div className="mt-1 font-mono text-[10.5px] uppercase tracking-[0.2em] text-ink-40">
                  key · {d.key}
                </div>
                <p className="mt-3 text-[13px] leading-relaxed text-ink-80">
                  {d.description}
                </p>
              </article>
            ))}
          </div>
          <div className="mt-6 rounded-lg border border-ink-10 bg-ink-5 p-4 font-mono text-[11px] text-ink-80">
            <span className="text-ink-40">Per-question scale:</span>{" "}
            {rubricS.data.per_question_scores.join(" · ")}
          </div>
        </section>
      )}

      {thresholdsS.data && rubricS.data && (
        <ThresholdsEditor
          id="thresholds"
          initial={thresholdsS.data}
          labels={rubricS.data.band_labels}
          onSaved={() => thresholdsS.mutate()}
        />
      )}

      {cutoffsS.data && (
        <TierCutoffsEditor
          id="tier-cutoffs"
          initial={cutoffsS.data}
          onSaved={() => cutoffsS.mutate()}
        />
      )}
    </div>
  );
}

function ThresholdsEditor({
  id,
  initial,
  labels,
  onSaved,
}: {
  id: string;
  initial: Thresholds;
  labels: Record<string, string>;
  onSaved: () => Promise<unknown> | void;
}) {
  const [draft, setDraft] = useState<Thresholds>(initial);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  useEffect(() => setDraft(initial), [initial]);

  const dirty =
    draft.trailblazer !== initial.trailblazer ||
    draft.qualifier !== initial.qualifier ||
    draft.developing !== initial.developing;

  const monotonic =
    draft.trailblazer > draft.qualifier && draft.qualifier > draft.developing;

  async function save() {
    setError(null);
    setSaving(true);
    try {
      await api.setThresholds(draft);
      setSavedAt(Date.now());
      await onSaved();
    } catch (e: unknown) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section
      id={id}
      className="border-t border-ink-10 px-6 py-10 md:px-10"
    >
      <div className="flex items-baseline justify-between">
        <h2 className="font-display text-[26px] text-ink-100">
          Performance bands
        </h2>
        <span className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-ink-40">
          PUT · /api/settings/thresholds
        </span>
      </div>
      <p className="mt-1 max-w-2xl text-[13px] text-ink-80">
        How aggregate percentages map to band labels on every report. Floors
        must descend.
      </p>
      <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <BandEditCard
          label={labels.TRBLZ ?? "Trailblazer"}
          tone="var(--lime)"
          value={draft.trailblazer}
          onChange={(n) => setDraft({ ...draft, trailblazer: n })}
        />
        <BandEditCard
          label={labels.QUALIF ?? "Qualifier"}
          tone="var(--cyan)"
          value={draft.qualifier}
          onChange={(n) => setDraft({ ...draft, qualifier: n })}
        />
        <BandEditCard
          label={labels.DEVLP ?? "Developing"}
          tone="var(--magenta)"
          value={draft.developing}
          onChange={(n) => setDraft({ ...draft, developing: n })}
        />
        <ReadOnlyBand
          label={labels["F-GAPS"] ?? "Foundational Gaps"}
          floor={0}
          tone="var(--ts-red)"
        />
      </div>
      <SaveBar
        dirty={dirty}
        valid={monotonic}
        saving={saving}
        error={error}
        savedAt={savedAt}
        invalidHint="Floors must descend: Trailblazer > Qualifier > Developing."
        onSave={save}
        onReset={() => setDraft(initial)}
      />
    </section>
  );
}

function TierCutoffsEditor({
  id,
  initial,
  onSaved,
}: {
  id: string;
  initial: TierCutoffs;
  onSaved: () => Promise<unknown> | void;
}) {
  const [draft, setDraft] = useState<TierCutoffs>(initial);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  useEffect(() => setDraft(initial), [initial]);

  const dirty = (["WA", "QA", "AA", "ZA"] as const).some(
    (t) => draft[t] !== initial[t],
  );

  async function save() {
    setError(null);
    setSaving(true);
    try {
      await api.setTierCutoffs(draft);
      setSavedAt(Date.now());
      await onSaved();
    } catch (e: unknown) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section id={id} className="border-t border-ink-10 px-6 py-10 md:px-10">
      <div className="flex items-baseline justify-between">
        <h2 className="font-display text-[26px] text-ink-100">
          Tier pass cutoffs
        </h2>
        <span className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-ink-40">
          PUT · /api/settings/tier-cutoffs
        </span>
      </div>
      <p className="mt-1 max-w-2xl text-[13px] text-ink-80">
        Passing a tier promotes a student to the next. AA is terminal — its
        cutoff is locked.
      </p>
      <div className="mt-6 grid gap-3 md:grid-cols-2">
        {(["WA", "QA", "AA", "ZA"] as const).map((t) => (
          <TierEditCard
            key={t}
            tier={t}
            value={draft[t]}
            terminal={t === "AA"}
            onChange={(n) => setDraft({ ...draft, [t]: n })}
          />
        ))}
      </div>
      <SaveBar
        dirty={dirty}
        valid={true}
        saving={saving}
        error={error}
        savedAt={savedAt}
        invalidHint=""
        onSave={save}
        onReset={() => setDraft(initial)}
      />
    </section>
  );
}

function BandEditCard({
  label,
  tone,
  value,
  onChange,
}: {
  label: string;
  tone: string;
  value: number;
  onChange: (n: number) => void;
}) {
  return (
    <div className="rounded-xl border border-ink-10 bg-[rgba(24,24,27,0.55)] p-4">
      <div
        className="font-mono text-[10.5px] uppercase tracking-[0.18em]"
        style={{ color: tone }}
      >
        {label}
      </div>
      <div className="mt-1 flex items-baseline gap-2">
        <input
          type="number"
          min={0}
          max={100}
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          className="w-[88px] bg-transparent font-display text-[32px] tabular-nums text-ink-100 outline-none focus:text-[var(--cyan)]"
        />
        <span className="font-mono text-[11px] text-ink-40">% and above</span>
      </div>
    </div>
  );
}

function ReadOnlyBand({
  label,
  floor,
  tone,
}: {
  label: string;
  floor: number;
  tone: string;
}) {
  return (
    <div className="rounded-xl border border-ink-10 bg-[rgba(24,24,27,0.4)] p-4">
      <div
        className="font-mono text-[10.5px] uppercase tracking-[0.18em]"
        style={{ color: tone }}
      >
        {label}
      </div>
      <div className="mt-1 flex items-baseline gap-2">
        <span className="font-display text-[32px] tabular-nums text-ink-40">
          {floor}
        </span>
        <span className="font-mono text-[11px] text-ink-40">
          % and above · floor locked
        </span>
      </div>
    </div>
  );
}

function TierEditCard({
  tier,
  value,
  terminal,
  onChange,
}: {
  tier: "WA" | "QA" | "AA" | "ZA";
  value: number | null;
  terminal: boolean;
  onChange: (n: number | null) => void;
}) {
  return (
    <div
      className={`rounded-xl border p-5 ${
        terminal
          ? "border-ink-10 bg-[rgba(24,24,27,0.4)]"
          : "border-ink-10 bg-[rgba(24,24,27,0.55)]"
      }`}
    >
      <div className="flex items-baseline justify-between">
        <h3 className="font-display text-[22px] text-ink-100">{tier}</h3>
        {terminal ? (
          <span className="font-mono text-[12px] text-ink-40">terminal</span>
        ) : (
          <div className="flex items-baseline gap-2">
            <span className="font-mono text-[11px] text-ink-40">pass ≥</span>
            <input
              type="number"
              min={0}
              max={100}
              value={value ?? ""}
              onChange={(e) =>
                onChange(e.target.value === "" ? null : Number(e.target.value))
              }
              placeholder="—"
              className="w-[80px] bg-transparent font-display text-[22px] tabular-nums text-[var(--lime)] outline-none focus:text-[var(--cyan)]"
            />
            <span className="font-mono text-[11px] text-ink-40">%</span>
          </div>
        )}
      </div>
      <p className="mt-2 text-[13px] text-ink-80">{TIER_DESCRIPTION[tier]}</p>
    </div>
  );
}

function SaveBar({
  dirty,
  valid,
  saving,
  error,
  savedAt,
  invalidHint,
  onSave,
  onReset,
}: {
  dirty: boolean;
  valid: boolean;
  saving: boolean;
  error: string | null;
  savedAt: number | null;
  invalidHint: string;
  onSave: () => void;
  onReset: () => void;
}) {
  const justSaved = savedAt && Date.now() - savedAt < 4000;

  return (
    <div className="mt-5 flex flex-wrap items-center gap-3">
      <button
        type="button"
        disabled={!dirty || !valid || saving}
        onClick={onSave}
        className="rounded-md border border-[rgba(190,242,100,0.4)] bg-[rgba(190,242,100,0.12)] px-3 py-[7px] font-sans text-[12px] font-medium text-ink-100 transition hover:bg-[rgba(190,242,100,0.2)] disabled:opacity-50"
      >
        {saving ? "Saving…" : "Save changes"}
      </button>
      <button
        type="button"
        disabled={!dirty || saving}
        onClick={onReset}
        className="rounded-md border border-ink-10 bg-ink-5 px-3 py-[7px] font-sans text-[12px] text-ink-80 transition hover:text-ink-100 disabled:opacity-50"
      >
        Reset
      </button>
      {!valid && dirty && (
        <span className="font-mono text-[11px] text-[var(--ts-red)]">
          {invalidHint}
        </span>
      )}
      {justSaved && !error && (
        <span className="font-mono text-[11px] text-[var(--lime)]">
          ✓ saved
        </span>
      )}
      {error && (
        <span className="font-mono text-[11px] text-[var(--ts-red)]">
          {error}
        </span>
      )}
    </div>
  );
}
