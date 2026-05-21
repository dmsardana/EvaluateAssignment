"use client";

import { useCallback, useEffect, useState } from "react";

/**
 * SSR-safe localStorage hook. Returns the default on the server and on the
 * first client render; hydrates from localStorage in an effect so React's
 * server/client trees stay aligned.
 */
export function useStoredState<T>(
  key: string,
  initial: T,
): [T, (next: T | ((prev: T) => T)) => void] {
  const [value, setValue] = useState<T>(initial);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(key);
      if (raw !== null) setValue(JSON.parse(raw) as T);
    } catch {
      /* localStorage disabled / corrupt entry — fall back to initial */
    }
  }, [key]);

  const update = useCallback(
    (next: T | ((prev: T) => T)) => {
      setValue((prev) => {
        const resolved =
          typeof next === "function" ? (next as (p: T) => T)(prev) : next;
        try {
          window.localStorage.setItem(key, JSON.stringify(resolved));
        } catch {
          /* persistence is best-effort */
        }
        return resolved;
      });
    },
    [key],
  );

  return [value, update];
}

export const drawerKey = {
  sectionOpen: (id: string, name: string) =>
    `ts:drawer:${id}:section:${name}:open`,
  model: (id: string) => `ts:drawer:${id}:model`,
};
