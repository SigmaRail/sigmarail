import { describe, expect, it } from "vitest";
import {
  FUNDAMENTALS_RAIL_STORAGE_KEY,
  loadFundamentalsRailOpen,
  saveFundamentalsRailOpen,
} from "./fundamentalsRailStorage";

class MemoryStorage implements Storage {
  private data = new Map<string, string>();

  get length() {
    return this.data.size;
  }

  clear() {
    this.data.clear();
  }

  getItem(key: string) {
    return this.data.has(key) ? this.data.get(key)! : null;
  }

  key(index: number) {
    return [...this.data.keys()][index] ?? null;
  }

  removeItem(key: string) {
    this.data.delete(key);
  }

  setItem(key: string, value: string) {
    this.data.set(key, value);
  }
}

describe("fundamentalsRailStorage", () => {
  it("defaults to open when missing", () => {
    expect(loadFundamentalsRailOpen(new MemoryStorage())).toBe(true);
  });

  it("reads a boolean payload", () => {
    const store = new MemoryStorage();
    store.setItem(FUNDAMENTALS_RAIL_STORAGE_KEY, "false");
    expect(loadFundamentalsRailOpen(store)).toBe(false);
  });

  it("round-trips { open } objects", () => {
    const store = new MemoryStorage();
    saveFundamentalsRailOpen(false, store);
    expect(loadFundamentalsRailOpen(store)).toBe(false);
    saveFundamentalsRailOpen(true, store);
    expect(loadFundamentalsRailOpen(store)).toBe(true);
    expect(JSON.parse(store.getItem(FUNDAMENTALS_RAIL_STORAGE_KEY) || "")).toEqual({
      open: true,
    });
  });
});
