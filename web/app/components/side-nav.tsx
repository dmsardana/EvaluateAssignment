"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

// Scope B runs auth-free on localhost. Replace this no-op with next-auth's
// signOut() when auth is reintroduced.
const signOut = (_: { callbackUrl: string }) => {
  console.warn("signOut() noop — auth not wired in Scope B");
};

interface NavItem {
  href: string;
  label: string;
  shortcut?: string;
  onClick?: () => void;
}

const CONSOLE: NavItem[] = [
  { href: "/", label: "Approval Queue", shortcut: "⌘1" },
  { href: "/assignments", label: "Assignments", shortcut: "⌘2" },
  { href: "/students", label: "Students", shortcut: "⌘3" },
  { href: "/reports", label: "Reports", shortcut: "⌘4" },
  { href: "/scores", label: "Scores", shortcut: "⌘5" },
];

const CONFIGURE: NavItem[] = [
  { href: "/rubric", label: "Rubric · 40·20·20·10·10" },
  { href: "/rubric#thresholds", label: "Band thresholds" },
  { href: "/rubric#tier-cutoffs", label: "Tier pass cutoffs" },
  { href: "/settings/classroom", label: "Classroom sync" },
  { href: "/settings/credentials", label: "Credentials" },
  { href: "/settings/report-views", label: "Report components" },
];

const ACCOUNT: NavItem[] = [
  { href: "/settings/workspace", label: "Workspace" },
  { href: "/settings/billing", label: "Billing" },
  { href: "/account/security", label: "Security" },
  {
    href: "#signout",
    label: "Sign out",
    onClick: () => signOut({ callbackUrl: "/login" }),
  },
];

export function SideNav({ onNavigate }: { onNavigate?: () => void } = {}) {
  const pathname = usePathname();
  const isActive = (href: string): boolean => {
    if (href === "/") return pathname === "/";
    if (href.includes("#")) return pathname === href.split("#")[0];
    return pathname === href || pathname.startsWith(href + "/");
  };

  return (
    <nav className="border-r border-ink-10 px-[18px] py-8">
      <Group title="Console" items={CONSOLE} isActive={isActive} onNavigate={onNavigate} />
      <Group title="Configure" items={CONFIGURE} isActive={isActive} onNavigate={onNavigate} />
      <Group title="Account" items={ACCOUNT} isActive={isActive} onNavigate={onNavigate} />
    </nav>
  );
}

function Group({
  title,
  items,
  isActive,
  onNavigate,
}: {
  title: string;
  items: NavItem[];
  isActive: (href: string) => boolean;
  onNavigate?: () => void;
}) {
  return (
    <div className="mb-7">
      <h6 className="mx-[14px] mb-[10px] font-mono text-[10px] font-medium uppercase tracking-[0.18em] text-ink-40">
        {title}
      </h6>
      {items.map((it) => {
        const active = isActive(it.href);
        const cls = `relative flex items-center justify-between rounded-[10px] px-[14px] py-[10px] font-sans text-[13px] font-medium transition ${
          active
            ? "bg-ink-10 text-ink-100 shadow-[inset_0_0_0_1px_var(--ink-10),0_0_24px_rgba(34,211,238,0.08)]"
            : "text-ink-80 hover:bg-ink-5 hover:text-ink-100"
        }`;
        const inner = (
          <>
            {active && (
              <span
                aria-hidden
                className="absolute left-[-4px] top-2 bottom-2 w-[2px] rounded-[1px]"
                style={{
                  background: "linear-gradient(180deg, var(--cyan), var(--violet))",
                }}
              />
            )}
            <span>{it.label}</span>
            {it.shortcut && (
              <span className="rounded bg-ink-5 px-[6px] py-[2px] font-mono text-[10px] text-ink-40">
                {it.shortcut}
              </span>
            )}
          </>
        );
        if (it.onClick) {
          return (
            <button
              key={it.href + it.label}
              type="button"
              onClick={() => {
                it.onClick?.();
                onNavigate?.();
              }}
              className={cls + " w-full text-left"}
            >
              {inner}
            </button>
          );
        }
        return (
          <Link
            key={it.href + it.label}
            href={it.href}
            onClick={() => onNavigate?.()}
            className={cls}
          >
            {inner}
          </Link>
        );
      })}
    </div>
  );
}
