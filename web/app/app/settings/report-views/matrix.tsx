"use client";

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

export function Matrix({
  catalog,
  tiers,
  draft,
  onChange,
  onResetTier,
}: Props) {
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
            <th key={t} className="px-2 text-center w-16">
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
          />
        ))}
        <tr className="border-t border-ink-10 font-medium">
          <td className="py-2 px-2">Per-tier totals</td>
          {tiers.map((t) => (
            <td key={t} className="text-center">
              {(draft[t] ?? []).length}
            </td>
          ))}
        </tr>
        <tr>
          <td className="py-2 px-2 text-ink-50">Reset to defaults</td>
          {tiers.map((t) => (
            <td key={t} className="text-center">
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
}: {
  category: string;
  rows: ReportComponentMeta[];
  tiers: string[];
  draft: Record<string, string[]>;
  onToggle: (tier: string, id: string) => void;
}) {
  return (
    <>
      <tr className="bg-ink-5">
        <td
          colSpan={tiers.length + 1}
          className="px-2 py-1 text-xs uppercase tracking-wide text-ink-50"
        >
          {category}
        </td>
      </tr>
      {rows.map((row) => (
        <tr key={row.id} className="border-b border-ink-5">
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
            return (
              <td key={t} className="text-center">
                <input
                  type="checkbox"
                  checked={checked || row.locked}
                  disabled={row.locked}
                  onChange={() => onToggle(t, row.id)}
                />
              </td>
            );
          })}
        </tr>
      ))}
    </>
  );
}
