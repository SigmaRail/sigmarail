export const FUNDAMENTALS_RAIL_STORAGE_KEY = "sigmarail-studio.fundamentals-rail.v1";

function resolveStorage(storage?: Storage | null): Storage | null {
  if (storage) return storage;
  try {
    if (typeof window !== "undefined") return window.localStorage;
  } catch {
    return null;
  }
  return null;
}

export function loadFundamentalsRailOpen(storage?: Storage | null): boolean {
  const store = resolveStorage(storage);
  if (!store) return true;
  try {
    const raw = store.getItem(FUNDAMENTALS_RAIL_STORAGE_KEY);
    if (raw === null) return true;
    const parsed = JSON.parse(raw);
    if (typeof parsed === "boolean") return parsed;
    if (parsed && typeof parsed === "object" && typeof parsed.open === "boolean") {
      return parsed.open;
    }
  } catch {
    return true;
  }
  return true;
}

export function saveFundamentalsRailOpen(open: boolean, storage?: Storage | null): void {
  const store = resolveStorage(storage);
  if (!store) return;
  try {
    store.setItem(FUNDAMENTALS_RAIL_STORAGE_KEY, JSON.stringify({ open }));
  } catch {
    // Ignore quota / privacy-mode failures.
  }
}
