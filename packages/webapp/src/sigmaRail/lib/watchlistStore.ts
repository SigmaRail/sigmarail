import { useState, useCallback, useEffect, useRef } from "react";
import { fetchWatchlistPreferences, saveWatchlistPreferences } from "../api/preferences";

export type WatchlistFlagColor = "red" | "green" | "yellow" | "blue" | "purple" | "none";

export interface WatchlistSymbolItem {
  ticker: string;
  flag?: WatchlistFlagColor;
  note?: string;
  added_at: string;
}

export interface Watchlist {
  id: string;
  name: string;
  is_system?: boolean;
  symbols: WatchlistSymbolItem[];
  created_at: string;
  updated_at: string;
}

const STORAGE_KEY = "sigmarail_studio_watchlists_v1";
const RECENT_KEY = "sigmarail_studio_recently_viewed_v1";
const LEGACY_STORAGE_KEY = "sigmarail_screening_studio_watchlists_v1";
const LEGACY_RECENT_KEY = "sigmarail_screening_studio_recently_viewed_v1";
const PRIOR_STORAGE_KEY = "sigmarail_studio_watchlists_v1";
const PROFILE_SAVE_DELAY_MS = 500;

const DEFAULT_WATCHLISTS: Watchlist[] = [
  {
    id: "tech_leaders",
    name: "Tech & Platform Leaders",
    symbols: [
      { ticker: "UBER", flag: "green", added_at: "2026-08-28" },
      { ticker: "LYFT", flag: "yellow", added_at: "2026-08-28" },
      { ticker: "DASH", flag: "red", added_at: "2026-08-28" },
      { ticker: "CRM", flag: "none", added_at: "2026-08-28" },
      { ticker: "NOW", flag: "none", added_at: "2026-08-28" },
      { ticker: "APP", flag: "green", added_at: "2026-08-28" },
      { ticker: "SHOP", flag: "none", added_at: "2026-08-28" },
    ],
    created_at: "2026-08-28",
    updated_at: "2026-08-28",
  },
  {
    id: "high_conviction",
    name: "High Conviction Compounders",
    symbols: [
      { ticker: "NVDA", flag: "green", note: "AI infrastructure leader", added_at: "2026-08-28" },
      { ticker: "UBER", flag: "green", note: "Fair value discount + CAGR > 30%", added_at: "2026-08-28" },
      { ticker: "V", flag: "blue", note: "Payment rail moat", added_at: "2026-08-28" },
      { ticker: "MA", flag: "blue", note: "Payment rail moat", added_at: "2026-08-28" },
    ],
    created_at: "2026-08-28",
    updated_at: "2026-08-28",
  },
];

export function getStoredWatchlists(userId: string | null): Watchlist[] {
  if (!userId) return DEFAULT_WATCHLISTS;
  try {
    const scopedKey = `${STORAGE_KEY}.${encodeURIComponent(userId)}`;
    const raw = localStorage.getItem(scopedKey) ??
      localStorage.getItem(PRIOR_STORAGE_KEY) ??
      localStorage.getItem(LEGACY_STORAGE_KEY);
    if (!raw) {
      return DEFAULT_WATCHLISTS;
    }
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed) && parsed.length > 0) {
      localStorage.setItem(scopedKey, JSON.stringify(parsed));
      localStorage.removeItem(PRIOR_STORAGE_KEY);
      localStorage.removeItem(LEGACY_STORAGE_KEY);
      return parsed;
    }
    return DEFAULT_WATCHLISTS;
  } catch {
    return DEFAULT_WATCHLISTS;
  }
}

export function saveStoredWatchlists(watchlists: Watchlist[], userId: string | null): void {
  if (!userId) return;
  try {
    localStorage.setItem(`${STORAGE_KEY}.${encodeURIComponent(userId)}`, JSON.stringify(watchlists));
    localStorage.removeItem(PRIOR_STORAGE_KEY);
    localStorage.removeItem(LEGACY_STORAGE_KEY);
  } catch (err) {
    console.error("Failed to save watchlists to localStorage:", err);
  }
}

export function getRecentlyViewed(): string[] {
  try {
    const raw = localStorage.getItem(RECENT_KEY) ?? localStorage.getItem(LEGACY_RECENT_KEY);
    return raw ? JSON.parse(raw) : ["LYFT", "UBER", "NVDA", "CRM"];
  } catch {
    return ["LYFT", "UBER", "NVDA", "CRM"];
  }
}

export function addRecentlyViewed(ticker: string): void {
  try {
    const clean = ticker.trim().toUpperCase();
    if (!clean) return;
    const current = getRecentlyViewed().filter((t) => t !== clean);
    const updated = [clean, ...current].slice(0, 20);
    localStorage.setItem(RECENT_KEY, JSON.stringify(updated));
    localStorage.removeItem(LEGACY_RECENT_KEY);
  } catch (err) {
    console.error("Failed to update recently viewed:", err);
  }
}

function normalizeProfileWatchlists(value: unknown): Watchlist[] | null {
  if (!Array.isArray(value)) return null;
  const valid = value.filter((item): item is Watchlist => {
    if (!item || typeof item !== "object") return false;
    const candidate = item as Partial<Watchlist>;
    return typeof candidate.id === "string" &&
      typeof candidate.name === "string" &&
      Array.isArray(candidate.symbols);
  });
  return valid.length > 0 ? valid : null;
}

/**
 * Custom React hook to manage watchlists reactively across the entire application
 */
export function useWatchlists() {
  const [watchlists, setWatchlists] = useState<Watchlist[]>(DEFAULT_WATCHLISTS);
  const [activeWatchlistId, setActiveWatchlistId] = useState<string>(() => {
    return DEFAULT_WATCHLISTS[0]?.id || "tech_leaders";
  });
  const watchlistsRef = useRef(watchlists);
  const profileUserIdRef = useRef<string | null>(null);
  const profileLoadedRef = useRef(false);
  const localChangesRef = useRef(false);
  const saveTimerRef = useRef<number | null>(null);

  const scheduleProfileSave = useCallback((next: Watchlist[]) => {
    if (saveTimerRef.current !== null) window.clearTimeout(saveTimerRef.current);
    saveTimerRef.current = window.setTimeout(() => {
      saveTimerRef.current = null;
      void saveWatchlistPreferences(next).catch(() => {
        // Keep local persistence as an offline fallback; retry on the next edit.
      });
    }, PROFILE_SAVE_DELAY_MS);
  }, []);

  useEffect(() => {
    let mounted = true;
    void fetchWatchlistPreferences()
      .then(({ userId, preferences: value }) => {
        if (!mounted) return;
        profileUserIdRef.current = userId;
        const remote = normalizeProfileWatchlists(value);
        profileLoadedRef.current = true;

        if (localChangesRef.current) {
          saveStoredWatchlists(watchlistsRef.current, userId);
          if (userId) scheduleProfileSave(watchlistsRef.current);
          return;
        }

        const selected = remote ?? getStoredWatchlists(userId);
        watchlistsRef.current = selected;
        setWatchlists(selected);
        saveStoredWatchlists(selected, userId);
        setActiveWatchlistId((current) => selected.some((list) => list.id === current) ? current : selected[0]?.id ?? "");
        if (!remote && userId) scheduleProfileSave(selected);
      })
      .catch(() => {
        // Preserve local use when the profile service is temporarily unavailable.
        if (!mounted) return;
        profileLoadedRef.current = true;
        if (localChangesRef.current && profileUserIdRef.current) scheduleProfileSave(watchlistsRef.current);
      });

    return () => {
      mounted = false;
      if (saveTimerRef.current !== null) {
        window.clearTimeout(saveTimerRef.current);
        saveTimerRef.current = null;
        if (profileUserIdRef.current) void saveWatchlistPreferences(watchlistsRef.current).catch(() => {
          // Local persistence remains available if navigation interrupts a profile save.
        });
      }
    };
  }, [scheduleProfileSave]);

  const activeWatchlist = watchlists.find((w) => w.id === activeWatchlistId) || watchlists[0];

  const updateWatchlists = useCallback((updater: (prev: Watchlist[]) => Watchlist[]) => {
    setWatchlists((prev) => {
      const next = updater(prev);
      watchlistsRef.current = next;
      localChangesRef.current = true;
      saveStoredWatchlists(next, profileUserIdRef.current);
      if (profileLoadedRef.current && profileUserIdRef.current) scheduleProfileSave(next);
      return next;
    });
  }, [scheduleProfileSave]);

  const createWatchlist = useCallback((name: string, initialSymbols: string[] = []): string => {
    const cleanName = name.trim();
    if (!cleanName) return "";
    const id = cleanName.toLowerCase().replace(/[^a-z0-9]+/g, "_") + "_" + Date.now().toString(36);
    const newItems: WatchlistSymbolItem[] = initialSymbols
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean)
      .map((ticker) => ({ ticker, added_at: new Date().toISOString().split("T")[0] }));

    const newList: Watchlist = {
      id,
      name: cleanName,
      symbols: newItems,
      created_at: new Date().toISOString().split("T")[0],
      updated_at: new Date().toISOString().split("T")[0],
    };

    updateWatchlists((prev) => [...prev, newList]);
    setActiveWatchlistId(id);
    return id;
  }, [updateWatchlists]);

  const deleteWatchlist = useCallback((id: string) => {
    updateWatchlists((prev) => {
      const filtered = prev.filter((w) => w.id !== id);
      if (filtered.length === 0) return DEFAULT_WATCHLISTS;
      return filtered;
    });
    setWatchlists((prev) => {
      const remaining = prev.filter((w) => w.id !== id);
      if (remaining.length > 0) setActiveWatchlistId(remaining[0].id);
      return remaining;
    });
  }, [updateWatchlists]);

  const renameWatchlist = useCallback((id: string, newName: string) => {
    const clean = newName.trim();
    if (!clean) return;
    updateWatchlists((prev) =>
      prev.map((w) => (w.id === id ? { ...w, name: clean, updated_at: new Date().toISOString().split("T")[0] } : w))
    );
  }, [updateWatchlists]);

  const addSymbol = useCallback((watchlistId: string, ticker: string, flag: WatchlistFlagColor = "none", note?: string) => {
    const clean = ticker.trim().toUpperCase();
    if (!clean) return;
    updateWatchlists((prev) =>
      prev.map((w) => {
        if (w.id !== watchlistId) return w;
        if (w.symbols.some((s) => s.ticker === clean)) {
          return {
            ...w,
            symbols: w.symbols.map((s) => (s.ticker === clean ? { ...s, flag: flag !== "none" ? flag : s.flag, note: note !== undefined ? note : s.note } : s)),
            updated_at: new Date().toISOString().split("T")[0],
          };
        }
        return {
          ...w,
          symbols: [{ ticker: clean, flag, note, added_at: new Date().toISOString().split("T")[0] }, ...w.symbols],
          updated_at: new Date().toISOString().split("T")[0],
        };
      })
    );
  }, [updateWatchlists]);

  const removeSymbol = useCallback((watchlistId: string, ticker: string) => {
    const clean = ticker.trim().toUpperCase();
    updateWatchlists((prev) =>
      prev.map((w) => {
        if (w.id !== watchlistId) return w;
        return {
          ...w,
          symbols: w.symbols.filter((s) => s.ticker !== clean),
          updated_at: new Date().toISOString().split("T")[0],
        };
      })
    );
  }, [updateWatchlists]);

  const setSymbolFlag = useCallback((watchlistId: string, ticker: string, flag: WatchlistFlagColor) => {
    const clean = ticker.trim().toUpperCase();
    updateWatchlists((prev) =>
      prev.map((w) => {
        if (w.id !== watchlistId) return w;
        return {
          ...w,
          symbols: w.symbols.map((s) => (s.ticker === clean ? { ...s, flag } : s)),
          updated_at: new Date().toISOString().split("T")[0],
        };
      })
    );
  }, [updateWatchlists]);

  const importTickers = useCallback((watchlistId: string, rawText: string) => {
    const tickers = rawText
      .split(/[\s,;\n\t]+/)
      .map((t) => t.trim().toUpperCase().replace(/[^A-Z0-9]/g, ""))
      .filter((t) => t.length > 0 && t.length <= 6);

    const uniqueTickers = Array.from(new Set(tickers));
    if (uniqueTickers.length === 0) return 0;

    updateWatchlists((prev) =>
      prev.map((w) => {
        if (w.id !== watchlistId) return w;
        const existingSet = new Set(w.symbols.map((s) => s.ticker));
        const newItems: WatchlistSymbolItem[] = uniqueTickers
          .filter((t) => !existingSet.has(t))
          .map((ticker) => ({ ticker, flag: "none", added_at: new Date().toISOString().split("T")[0] }));
        return {
          ...w,
          symbols: [...w.symbols, ...newItems],
          updated_at: new Date().toISOString().split("T")[0],
        };
      })
    );
    return uniqueTickers.length;
  }, [updateWatchlists]);

  const exportWatchlist = useCallback((watchlistId: string, format: "csv" | "text" | "json" = "text"): string => {
    const list = watchlists.find((w) => w.id === watchlistId);
    if (!list) return "";
    if (format === "json") {
      return JSON.stringify(list, null, 2);
    }
    if (format === "csv") {
      const header = "Ticker,Flag,Note,AddedAt\n";
      const rows = list.symbols.map((s) => `"${s.ticker}","${s.flag || "none"}","${s.note || ""}","${s.added_at}"`).join("\n");
      return header + rows;
    }
    return list.symbols.map((s) => s.ticker).join(", ");
  }, [watchlists]);

  return {
    watchlists,
    activeWatchlistId,
    activeWatchlist,
    setActiveWatchlistId,
    createWatchlist,
    deleteWatchlist,
    renameWatchlist,
    addSymbol,
    removeSymbol,
    setSymbolFlag,
    importTickers,
    exportWatchlist,
  };
}
