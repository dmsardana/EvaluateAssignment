"use client";

import { useEffect, useState } from "react";

import { SideNav } from "./side-nav";
import { TopBar } from "./top-bar";

export function Shell({ children }: { children: React.ReactNode }) {
  const [drawerOpen, setDrawerOpen] = useState(false);

  // Lock body scroll while drawer is open on mobile.
  useEffect(() => {
    document.body.style.overflow = drawerOpen ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [drawerOpen]);

  return (
    <div className="min-h-screen">
      <TopBar onMenuClick={() => setDrawerOpen((s) => !s)} />

      <div className="lg:grid lg:grid-cols-[260px_1fr]">
        {/* Desktop sidenav */}
        <aside className="hidden lg:block lg:sticky lg:top-0 lg:h-[calc(100vh-78px)] lg:overflow-y-auto">
          <SideNav />
        </aside>

        {/* Mobile drawer */}
        {drawerOpen && (
          <>
            <div
              className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm lg:hidden"
              onClick={() => setDrawerOpen(false)}
              aria-hidden
            />
            <aside className="fixed left-0 top-0 z-50 h-full w-[280px] overflow-y-auto bg-[#0a0a0b] lg:hidden">
              <div className="flex items-center justify-between px-4 py-4">
                <span className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-ink-40">
                  Navigate
                </span>
                <button
                  type="button"
                  aria-label="Close navigation"
                  onClick={() => setDrawerOpen(false)}
                  className="grid h-8 w-8 place-items-center rounded-lg border border-ink-10 bg-ink-5 text-ink-80"
                >
                  ×
                </button>
              </div>
              <SideNav onNavigate={() => setDrawerOpen(false)} />
            </aside>
          </>
        )}

        <main className="min-w-0">{children}</main>
      </div>
    </div>
  );
}
