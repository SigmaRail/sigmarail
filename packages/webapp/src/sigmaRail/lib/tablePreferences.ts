import { useCallback } from "react";
import { useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import {
  fetchTablePreferences,
  saveTablePreferences,
  type TablePreferences,
  type TableViewPreferences,
} from "../api/preferences";

const TABLE_PREFERENCES_QUERY_KEY = ["profile-preferences", "tables"] as const;
const LEGACY_COLUMN_KEY_PREFIX = "sigmarail-studio.table-cols.";
const LEGACY_DENSITY_KEY_PREFIX = "sigmarail-studio.table-density.";
const PROFILE_SAVE_DELAY_MS = 500;
const saveTimers = new WeakMap<QueryClient, number>();

type LoadedTablePreferences = {
  userId: string | null;
  preferences: TablePreferences;
};

function parseColumnVisibility(value: string | null): Record<string, boolean> | undefined {
  if (!value) return undefined;
  try {
    const parsed: unknown = JSON.parse(value);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return undefined;
    return Object.fromEntries(
      Object.entries(parsed).filter((entry): entry is [string, boolean] => typeof entry[1] === "boolean"),
    );
  } catch {
    return undefined;
  }
}

function scopedKeyPrefix(userId: string, kind: "cols" | "density"): string {
  return `sigmarail-studio.user.${encodeURIComponent(userId)}.table-${kind}.`;
}

function readStoredPreferences(columnPrefix: string, densityPrefix: string): TablePreferences {
  const preferences: TablePreferences = {};
  try {
    for (let index = 0; index < localStorage.length; index += 1) {
      const key = localStorage.key(index);
      if (!key) continue;
      if (key.startsWith(columnPrefix)) {
        const viewId = key.slice(columnPrefix.length);
        const columns = parseColumnVisibility(localStorage.getItem(key));
        if (columns) preferences[viewId] = { ...preferences[viewId], columns };
      } else if (key.startsWith(densityPrefix)) {
        const density = localStorage.getItem(key);
        if (density === "compact" || density === "comfortable") {
          const viewId = key.slice(densityPrefix.length);
          preferences[viewId] = { ...preferences[viewId], density };
        }
      }
    }
  } catch {
    // Browser-local settings remain optional when storage is disabled.
  }
  return preferences;
}

function removeLegacyPreferences(): void {
  try {
    const keys: string[] = [];
    for (let index = 0; index < localStorage.length; index += 1) {
      const key = localStorage.key(index);
      if (key?.startsWith(LEGACY_COLUMN_KEY_PREFIX) || key?.startsWith(LEGACY_DENSITY_KEY_PREFIX)) {
        keys.push(key);
      }
    }
    keys.forEach((key) => localStorage.removeItem(key));
  } catch {
    // Legacy keys are optional and cannot affect profile-backed settings.
  }
}

export function loadStoredTablePreferences(userId: string | null): TablePreferences {
  if (!userId) return {};
  const columnPrefix = scopedKeyPrefix(userId, "cols");
  const densityPrefix = scopedKeyPrefix(userId, "density");
  const scoped = readStoredPreferences(columnPrefix, densityPrefix);
  if (Object.keys(scoped).length > 0) {
    removeLegacyPreferences();
    return scoped;
  }

  const legacy = readStoredPreferences(LEGACY_COLUMN_KEY_PREFIX, LEGACY_DENSITY_KEY_PREFIX);
  if (Object.keys(legacy).length === 0) return legacy;
  for (const [viewId, preference] of Object.entries(legacy)) {
    saveStoredTableViewPreferences(viewId, preference, userId);
  }
  removeLegacyPreferences();
  return legacy;
}

export function saveStoredTableViewPreferences(
  viewId: string,
  update: TableViewPreferences,
  userId: string | null,
): void {
  if (!userId) return;
  try {
    if (update.columns) {
      localStorage.setItem(`${scopedKeyPrefix(userId, "cols")}${viewId}`, JSON.stringify(update.columns));
    }
    if (update.density) {
      localStorage.setItem(`${scopedKeyPrefix(userId, "density")}${viewId}`, update.density);
    }
  } catch {
    // Continue with the account profile when browser storage is unavailable.
  }
}

async function loadProfileTablePreferences(): Promise<LoadedTablePreferences> {
  const profile = await fetchTablePreferences();
  const stored = loadStoredTablePreferences(profile.userId);
  const remote = profile.preferences ?? {};
  // Profile data is authoritative when present; retain account-scoped local
  // values only for fields the profile has not received yet (for example an
  // edit made while the profile save request was offline).
  const preferences: TablePreferences = { ...stored };
  for (const [viewId, preference] of Object.entries(remote)) {
    preferences[viewId] = { ...stored[viewId], ...preference };
  }

  if (profile.userId && JSON.stringify(preferences) !== JSON.stringify(remote)) {
    try {
      await saveTablePreferences(preferences);
    } catch {
      // The local copy remains available for offline or temporarily unavailable profile service.
    }
  }
  return { userId: profile.userId, preferences };
}

export function useTableViewPreferences(viewId: string) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: TABLE_PREFERENCES_QUERY_KEY,
    queryFn: loadProfileTablePreferences,
    staleTime: Infinity,
    retry: 1,
  });

  const save = useCallback((update: TableViewPreferences) => {
    const current = queryClient.getQueryData<LoadedTablePreferences>(TABLE_PREFERENCES_QUERY_KEY)
      ?? query.data
      ?? { userId: null, preferences: {} };
    const next: LoadedTablePreferences = {
      ...current,
      preferences: {
        ...current.preferences,
        [viewId]: { ...current.preferences[viewId], ...update },
      },
    };
    queryClient.setQueryData(TABLE_PREFERENCES_QUERY_KEY, next);
    saveStoredTableViewPreferences(viewId, update, next.userId);

    const previousTimer = saveTimers.get(queryClient);
    if (previousTimer !== undefined) window.clearTimeout(previousTimer);
    saveTimers.set(queryClient, window.setTimeout(() => {
      saveTimers.delete(queryClient);
      const latest = queryClient.getQueryData<LoadedTablePreferences>(TABLE_PREFERENCES_QUERY_KEY) ?? next;
      if (!latest.userId) return;
      void saveTablePreferences(latest.preferences).catch(() => {
        // The browser copy remains available and the next edit retries the profile save.
      });
    }, PROFILE_SAVE_DELAY_MS));
  }, [query.data, queryClient, viewId]);

  return {
    loaded: query.isSuccess,
    preference: query.data?.preferences[viewId],
    userId: query.data?.userId ?? null,
    save,
  };
}
