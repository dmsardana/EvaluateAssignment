"use client";

import { useMemo } from "react";

import { drawerKey, useStoredState } from "@/lib/preferences";

export type Provider = "anthropic" | "gemini" | "openai";

interface ModelOption {
  id: string;
  label: string;
}

interface ProviderInfo {
  label: string;
  models: ModelOption[];
  wired: boolean;
  hint?: string;
}

export const PROVIDERS: Record<Provider, ProviderInfo> = {
  anthropic: {
    label: "Anthropic",
    wired: true,
    models: [
      { id: "claude-opus-4-7", label: "Claude Opus 4.7" },
      { id: "claude-sonnet-4-6", label: "Claude Sonnet 4.6" },
      { id: "claude-haiku-4-5-20251001", label: "Claude Haiku 4.5" },
    ],
  },
  gemini: {
    label: "Gemini",
    wired: true,
    hint: "Requires GEMINI_API_KEY (Settings · Credentials).",
    models: [
      { id: "gemini-2.5-pro", label: "Gemini 2.5 Pro" },
      { id: "gemini-2.5-flash", label: "Gemini 2.5 Flash" },
      { id: "gemini-2.0-pro", label: "Gemini 2.0 Pro" },
      { id: "gemini-2.0-flash", label: "Gemini 2.0 Flash" },
    ],
  },
  openai: {
    label: "OpenAI",
    wired: true,
    hint: "Requires OPENAI_API_KEY (Settings · Credentials).",
    models: [
      { id: "gpt-4o", label: "GPT-4o" },
      { id: "gpt-4o-mini", label: "GPT-4o mini" },
      { id: "o1", label: "o1 (reasoning)" },
      { id: "o1-mini", label: "o1 mini" },
    ],
  },
};

export interface ModelSelection {
  provider: Provider;
  model: string;
}

function parse(stored: string): ModelSelection {
  const [p, ...rest] = stored.split(":");
  const provider = (["anthropic", "gemini", "openai"].includes(p)
    ? p
    : "anthropic") as Provider;
  const model = rest.join(":") || PROVIDERS[provider].models[0].id;
  return { provider, model };
}

function encode(sel: ModelSelection): string {
  return `${sel.provider}:${sel.model}`;
}

interface Props {
  courseworkId: string;
  defaultModel?: string | null;
  onChange?: (sel: ModelSelection) => void;
}

export function ModelPicker({ courseworkId, defaultModel, onChange }: Props) {
  const initialEncoded = useMemo(() => {
    if (!defaultModel) return "anthropic:claude-sonnet-4-6";
    for (const p of Object.keys(PROVIDERS) as Provider[]) {
      if (PROVIDERS[p].models.some((m) => m.id === defaultModel)) {
        return `${p}:${defaultModel}`;
      }
    }
    return `anthropic:${defaultModel}`;
  }, [defaultModel]);

  const [stored, setStored] = useStoredState<string>(
    drawerKey.model(courseworkId),
    initialEncoded,
  );
  const sel = parse(stored);
  const info = PROVIDERS[sel.provider];

  function update(next: ModelSelection) {
    setStored(encode(next));
    onChange?.(next);
  }

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-xl border border-ink-10 bg-[rgba(24,24,27,0.6)] p-3">
      <div className="flex items-baseline gap-2">
        <label
          htmlFor="provider"
          className="font-mono text-[10px] uppercase tracking-[0.2em] text-ink-40"
        >
          Provider
        </label>
        <select
          id="provider"
          value={sel.provider}
          onChange={(e) => {
            const provider = e.target.value as Provider;
            update({ provider, model: PROVIDERS[provider].models[0].id });
          }}
          className="rounded-md border border-ink-10 bg-ink-5 px-3 py-[6px] font-sans text-[12px] text-ink-100 outline-none focus:border-cyan"
        >
          {(Object.keys(PROVIDERS) as Provider[]).map((p) => (
            <option key={p} value={p}>
              {PROVIDERS[p].label}
              {PROVIDERS[p].wired ? "" : " · not wired"}
            </option>
          ))}
        </select>
      </div>

      <div className="flex items-baseline gap-2">
        <label
          htmlFor="model"
          className="font-mono text-[10px] uppercase tracking-[0.2em] text-ink-40"
        >
          Model
        </label>
        <select
          id="model"
          value={sel.model}
          onChange={(e) =>
            update({ provider: sel.provider, model: e.target.value })
          }
          className="rounded-md border border-ink-10 bg-ink-5 px-3 py-[6px] font-sans text-[12px] text-ink-100 outline-none focus:border-cyan"
        >
          {info.models.map((m) => (
            <option key={m.id} value={m.id}>
              {m.label}
            </option>
          ))}
        </select>
      </div>

      <span
        className={`font-mono text-[10.5px] uppercase tracking-[0.18em] ${
          info.wired ? "text-[var(--lime)]" : "text-[var(--magenta)]"
        }`}
      >
        {info.wired ? "wired" : "ui only"}
      </span>

      {info.hint && (
        <span className="text-[11px] text-ink-40">{info.hint}</span>
      )}
    </div>
  );
}

/** Read the current selection synchronously (e.g. at click-time on Evaluate). */
export function selectionFromStored(
  courseworkId: string,
  defaultModel?: string | null,
): ModelSelection {
  if (typeof window === "undefined") {
    return {
      provider: "anthropic",
      model: defaultModel ?? "claude-sonnet-4-6",
    };
  }
  const raw = window.localStorage.getItem(drawerKey.model(courseworkId));
  if (raw) {
    try {
      return parse(JSON.parse(raw) as string);
    } catch {
      /* fall through */
    }
  }
  return parse(`anthropic:${defaultModel ?? "claude-sonnet-4-6"}`);
}
