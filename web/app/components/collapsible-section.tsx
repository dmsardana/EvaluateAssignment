"use client";

import { drawerKey, useStoredState } from "@/lib/preferences";

interface CollapsibleSectionProps {
  courseworkId: string;
  name: string;
  title: string;
  sub?: React.ReactNode;
  defaultOpen?: boolean;
  children: React.ReactNode;
  toolbar?: React.ReactNode;
}

export function CollapsibleSection({
  courseworkId,
  name,
  title,
  sub,
  defaultOpen = true,
  children,
  toolbar,
}: CollapsibleSectionProps) {
  const [open, setOpen] = useStoredState<boolean>(
    drawerKey.sectionOpen(courseworkId, name),
    defaultOpen,
  );

  return (
    <section className="border-t border-ink-10">
      <header className="flex flex-wrap items-baseline gap-3 px-6 pb-3 pt-8 md:px-10">
        <button
          type="button"
          onClick={() => setOpen((s) => !s)}
          aria-expanded={open}
          className="group inline-flex items-baseline gap-3"
        >
          <span
            aria-hidden
            className={`inline-block h-[10px] w-[10px] rounded-sm border border-ink-40 transition group-hover:border-ink-100 ${
              open
                ? "bg-[var(--ts-red)] border-[var(--ts-red)]"
                : "bg-transparent"
            }`}
          />
          <h2 className="font-display text-[22px] text-ink-100 transition group-hover:text-[var(--ts-red)]">
            {title}
          </h2>
        </button>
        {sub && (
          <span className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-ink-40">
            {sub}
          </span>
        )}
        {toolbar && (
          <div className="ml-auto flex flex-wrap items-center gap-2">
            {toolbar}
          </div>
        )}
      </header>
      {open && (
        <div className="px-6 pb-10 md:px-10" data-section-name={name}>
          {children}
        </div>
      )}
    </section>
  );
}
