"use client";

import "katex/dist/katex.min.css";
import { BlockMath, InlineMath } from "react-katex";

/**
 * Render a string that may contain `$...$` (inline) and `$$...$$` (block)
 * LaTeX. Everything outside math delimiters is plain text. KaTeX parse
 * errors fall back to monospace so the operator still sees the raw source.
 */
export function MathText({
  children,
  className = "",
}: {
  children: string;
  className?: string;
}) {
  const parts = splitMath(children);
  return (
    <span className={className}>
      {parts.map((p, i) => {
        if (p.kind === "text") {
          return <span key={i}>{p.value}</span>;
        }
        const Component = p.kind === "block" ? BlockMath : InlineMath;
        try {
          return (
            <Component
              key={i}
              math={p.value}
              renderError={(err: Error) => (
                <code
                  className="font-mono text-[12px] text-[var(--ts-red)]"
                  title={err.message}
                >
                  {p.kind === "block" ? "$$" : "$"}
                  {p.value}
                  {p.kind === "block" ? "$$" : "$"}
                </code>
              )}
            />
          );
        } catch {
          return (
            <code key={i} className="font-mono text-[12px] text-ink-40">
              {p.value}
            </code>
          );
        }
      })}
    </span>
  );
}

type Part = { kind: "text" | "inline" | "block"; value: string };

function splitMath(s: string): Part[] {
  const out: Part[] = [];
  let i = 0;
  while (i < s.length) {
    if (s[i] === "$" && s[i + 1] === "$") {
      const end = s.indexOf("$$", i + 2);
      if (end !== -1) {
        out.push({ kind: "block", value: s.slice(i + 2, end) });
        i = end + 2;
        continue;
      }
    }
    if (s[i] === "$") {
      const end = s.indexOf("$", i + 1);
      if (end !== -1) {
        out.push({ kind: "inline", value: s.slice(i + 1, end) });
        i = end + 1;
        continue;
      }
    }
    let j = i;
    while (j < s.length && s[j] !== "$") j += 1;
    out.push({ kind: "text", value: s.slice(i, j) });
    i = j;
  }
  return out;
}
