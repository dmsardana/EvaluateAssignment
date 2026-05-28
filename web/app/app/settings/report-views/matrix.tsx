"use client";

import { useState } from "react";

import { ReportComponentMeta } from "@/lib/api";

type Props = {
  catalog: ReportComponentMeta[];
  tiers: string[];
  draft: Record<string, string[]>;
  onChange: (next: Record<string, string[]>) => void;
  onResetTier: (tier: string) => void;
};

const CATEGORY_ORDER = [
  "Structural",
  "Score",
  "Diagnostic",
  "Coaching",
  "Action",
  "Quality",
  "Engagement",
];

// Category-specific accent. The colored left strip sells "new section" at a
// glance; the row itself stays neutral so the checkbox grid stays the focus.
const CATEGORY_ACCENT: Record<string, { strip: string; label: string }> = {
  Structural:  { strip: "border-l-zinc-400",    label: "text-zinc-300" },
  Score:       { strip: "border-l-rose-500",    label: "text-rose-300" },
  Diagnostic:  { strip: "border-l-sky-500",     label: "text-sky-300" },
  Coaching:    { strip: "border-l-amber-500",   label: "text-amber-300" },
  Action:      { strip: "border-l-emerald-500", label: "text-emerald-300" },
  Quality:     { strip: "border-l-violet-500",  label: "text-violet-300" },
  Engagement:  { strip: "border-l-teal-500",    label: "text-teal-300" },
};
const DEFAULT_ACCENT = { strip: "border-l-ink-30", label: "text-ink-60" };

export function Matrix({
  catalog,
  tiers,
  draft,
  onChange,
  onResetTier,
}: Props) {
  const [hoverRow, setHoverRow] = useState<string | null>(null);
  const [hoverTier, setHoverTier] = useState<string | null>(null);

  const grouped = new Map<string, ReportComponentMeta[]>();
  for (const c of catalog) {
    const list = grouped.get(c.category) ?? [];
    list.push(c);
    grouped.set(c.category, list);
  }
  const knownCats = CATEGORY_ORDER.filter((c) => grouped.has(c));
  const otherCats = Array.from(grouped.keys()).filter(
    (c) => !CATEGORY_ORDER.includes(c),
  );
  const categories = [...knownCats, ...otherCats];

  function toggle(tier: string, id: string) {
    const set = new Set(draft[tier] ?? []);
    if (set.has(id)) set.delete(id);
    else set.add(id);
    onChange({ ...draft, [tier]: Array.from(set) });
  }

  return (
    <table className="w-full text-sm border-collapse">
      <thead>
        <tr className="border-b border-ink-10">
          <th className="text-left py-2 px-2">Component</th>
          {tiers.map((t) => (
            <th
              key={t}
              className={`px-2 text-center w-16 transition-colors duration-100 ${
                hoverTier === t ? "bg-ink-10 text-ink-90" : ""
              }`}
              onMouseEnter={() => setHoverTier(t)}
              onMouseLeave={() => setHoverTier(null)}
            >
              {t}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {categories.map((cat) => (
          <CategoryGroup
            key={cat}
            category={cat}
            rows={grouped.get(cat)!}
            tiers={tiers}
            draft={draft}
            onToggle={toggle}
            hoverRow={hoverRow}
            hoverTier={hoverTier}
            setHoverRow={setHoverRow}
            setHoverTier={setHoverTier}
          />
        ))}
        <tr className="border-t border-ink-10 font-medium">
          <td className="py-2 px-2">Per-tier totals</td>
          {tiers.map((t) => (
            <td
              key={t}
              className={`text-center transition-colors duration-100 ${
                hoverTier === t ? "bg-ink-10" : ""
              }`}
            >
              {(draft[t] ?? []).length}
            </td>
          ))}
        </tr>
        <tr>
          <td className="py-2 px-2 text-ink-50">Reset to defaults</td>
          {tiers.map((t) => (
            <td
              key={t}
              className={`text-center transition-colors duration-100 ${
                hoverTier === t ? "bg-ink-10" : ""
              }`}
            >
              <button
                onClick={() => onResetTier(t)}
                className="text-xs underline text-sky-400 hover:text-sky-300"
              >
                reset
              </button>
            </td>
          ))}
        </tr>
      </tbody>
    </table>
  );
}

function CategoryGroup({
  category,
  rows,
  tiers,
  draft,
  onToggle,
  hoverRow,
  hoverTier,
  setHoverRow,
  setHoverTier,
}: {
  category: string;
  rows: ReportComponentMeta[];
  tiers: string[];
  draft: Record<string, string[]>;
  onToggle: (tier: string, id: string) => void;
  hoverRow: string | null;
  hoverTier: string | null;
  setHoverRow: (id: string | null) => void;
  setHoverTier: (t: string | null) => void;
}) {
  const a = CATEGORY_ACCENT[category] ?? DEFAULT_ACCENT;
  return (
    <>
      <tr>
        <td
          colSpan={tiers.length + 1}
          className={`border-l-4 ${a.strip} bg-ink-5 pl-3 pr-2 py-2`}
        >
          <span
            className={`text-[11px] font-semibold uppercase tracking-[0.18em] ${a.label}`}
          >
            {category}
          </span>
        </td>
      </tr>
      {rows.map((row) => {
        const isRow = hoverRow === row.id;
        return (
          <tr
            key={row.id}
            className={`border-b border-ink-5 transition-colors duration-100 ${
              isRow ? "bg-ink-10" : ""
            }`}
            onMouseEnter={() => setHoverRow(row.id)}
            onMouseLeave={() => setHoverRow(null)}
          >
            <td className="px-2 py-1">
              <span title={row.description}>
                {row.locked ? "🔒 " : ""}
                {row.label}
                {row.default_off ? (
                  <span className="ml-2 text-[10px] uppercase tracking-wide text-ink-40">
                    proposed
                  </span>
                ) : null}
              </span>
            </td>
            {tiers.map((t) => {
              const checked = (draft[t] ?? []).includes(row.id);
              const isCol = hoverTier === t;
              const cellBg =
                isRow && isCol ? "bg-ink-20" : isCol ? "bg-ink-10" : "";
              return (
                <td
                  key={t}
                  className={`text-center transition-colors duration-100 ${cellBg}`}
                  onMouseEnter={() => setHoverTier(t)}
                  onMouseLeave={() => setHoverTier(null)}
                >
                  <input
                    type="checkbox"
                    checked={checked || row.locked}
                    disabled={row.locked}
                    onChange={() => onToggle(t, row.id)}
                    className="transition-transform duration-100 hover:scale-110"
                  />
                </td>
              );
            })}
          </tr>
        );
      })}
    </>
  );
}
