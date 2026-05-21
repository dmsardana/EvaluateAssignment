// Academic Year math — Indian AY runs Apr 1 → Mar 31 of the next year.
// `AY 2026-27` means Apr 1 2026 through Mar 31 2027.

export function ayStartYear(d: Date): number {
  // Months are 0-indexed in JS — Apr is month 3.
  return d.getMonth() >= 3 ? d.getFullYear() : d.getFullYear() - 1;
}

export function ayLabel(startYear: number): string {
  const end = (startYear + 1).toString().slice(-2);
  return `AY ${startYear}-${end}`;
}

export function ayRange(startYear: number): { from: string; to: string } {
  // Returns ISO date strings (YYYY-MM-DD) — what <input type="date"> wants.
  return {
    from: `${startYear}-04-01`,
    to: `${startYear + 1}-03-31`,
  };
}

// Default AY options for the dropdown — a generous range around the
// current AY so operators can look back at past years (review historical
// scores) and forward at the next (plan next session) even when no data
// has been recorded yet. Pages can union this with AYs observed in their
// data via `unionAyOptions`.
export function defaultAyOptions(
  today: Date,
  lookback = 5,
  lookahead = 1,
): number[] {
  const start = ayStartYear(today);
  const out: number[] = [];
  for (let i = -lookback; i <= lookahead; i++) out.push(start + i);
  return out;
}

// Merge default range with any AYs derived from actual data; newest first.
export function unionAyOptions(
  defaults: number[],
  observed: Iterable<number>,
): number[] {
  return [...new Set([...defaults, ...observed])].sort((a, b) => b - a);
}

export function parseDate(s: string | null | undefined): Date | null {
  if (!s) return null;
  const t = Date.parse(s);
  return Number.isNaN(t) ? null : new Date(t);
}

// Inclusive [from, to] range check against an ISO date string. Undated
// inputs return true so they remain visible — callers can layer their
// own "drop undated" policy on top if desired.
export function inDateRange(
  s: string | null | undefined,
  fromIso: string,
  toIso: string,
): boolean {
  const d = parseDate(s);
  if (!d) return true;
  const from = parseDate(fromIso);
  const to = parseDate(toIso);
  if (from && d < from) return false;
  if (to && d > to) return false;
  return true;
}
