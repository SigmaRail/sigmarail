import { authenticatedFetch } from "./authenticatedFetch";
import type { ChartSettingsV2 } from "../lib/chartSettings";

type GraphQLResponse<T> = {
  data?: T;
  errors?: Array<{ message?: string }>;
};

async function executeGraphQL<T>(query: string, variables?: Record<string, unknown>): Promise<T> {
  const response = await authenticatedFetch("/api/graphql/", {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ query, variables }),
  });
  const payload = await response.json().catch(() => null) as GraphQLResponse<T> | null;
  if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);
  if (payload?.errors?.length) {
    throw new Error(payload.errors.map((error) => error.message || "GraphQL request failed").join("; "));
  }
  if (!payload?.data) throw new Error("The GraphQL server returned no data");
  return payload.data;
}

function parsePreferences(value: unknown): ChartSettingsV2 | null {
  if (typeof value === "string") {
    try {
      value = JSON.parse(value);
    } catch {
      return null;
    }
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as ChartSettingsV2;
}

export async function fetchChartPreferences(): Promise<{ userId: string | null; settings: ChartSettingsV2 | null; configured: boolean }> {
  const data = await executeGraphQL<{ currentUser?: { id?: string | null; chartPreferences?: unknown } | null }>(`
    query SigmaRailChartPreferences {
      currentUser {
        id
        chartPreferences
      }
    }
  `);
  const settings = parsePreferences(data.currentUser?.chartPreferences);
  const configured = settings !== null && Object.keys(settings).length > 0;
  return { userId: data.currentUser?.id ?? null, settings, configured };
}

export async function saveChartPreferences(settings: ChartSettingsV2): Promise<void> {
  await executeGraphQL(`
    mutation SaveSigmaRailChartPreferences($input: UpdateCurrentUserMutationInput!) {
      updateCurrentUser(input: $input) {
        userProfile {
          id
        }
      }
    }
  `, { input: { chartPreferences: JSON.stringify(settings) } });
}

export async function fetchWatchlistPreferences(): Promise<{ userId: string | null; preferences: unknown }> {
  const data = await executeGraphQL<{ currentUser?: { id?: string | null; watchlistPreferences?: unknown } | null }>(`
    query SigmaRailWatchlistPreferences {
      currentUser {
        id
        watchlistPreferences
      }
    }
  `);
  const value = data.currentUser?.watchlistPreferences;
  let preferences: unknown;
  if (typeof value === "string") {
    try {
      preferences = JSON.parse(value);
    } catch {
      preferences = null;
    }
  } else {
    preferences = value ?? null;
  }
  return { userId: data.currentUser?.id ?? null, preferences };
}

export async function saveWatchlistPreferences(watchlists: unknown): Promise<void> {
  await executeGraphQL(`
    mutation SaveSigmaRailWatchlistPreferences($input: UpdateCurrentUserMutationInput!) {
      updateCurrentUser(input: $input) {
        userProfile {
          id
        }
      }
    }
  `, { input: { watchlistPreferences: JSON.stringify(watchlists) } });
}

export type TableViewPreferences = {
  columns?: Record<string, boolean>;
  density?: "compact" | "comfortable";
};
export type TablePreferences = Record<string, TableViewPreferences>;

export async function fetchTablePreferences(): Promise<{ userId: string | null; preferences: TablePreferences | null }> {
  const data = await executeGraphQL<{ currentUser?: { id?: string | null; tablePreferences?: unknown } | null }>(`
    query SigmaRailTablePreferences {
      currentUser {
        id
        tablePreferences
      }
    }
  `);
  let value = data.currentUser?.tablePreferences;
  if (typeof value === "string") {
    try {
      value = JSON.parse(value);
    } catch {
      return { userId: data.currentUser?.id ?? null, preferences: null };
    }
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return { userId: data.currentUser?.id ?? null, preferences: null };
  }
  return { userId: data.currentUser?.id ?? null, preferences: value as TablePreferences };
}

export async function saveTablePreferences(preferences: TablePreferences): Promise<void> {
  await executeGraphQL(`
    mutation SaveSigmaRailTablePreferences($input: UpdateCurrentUserMutationInput!) {
      updateCurrentUser(input: $input) {
        userProfile {
          id
        }
      }
    }
  `, { input: { tablePreferences: JSON.stringify(preferences) } });
}

export async function fetchBenchmarkPreferences(): Promise<{ userId: string | null; preferences: string[] | null }> {
  const data = await executeGraphQL<{ currentUser?: { id?: string | null; benchmarkPreferences?: unknown } | null }>(`
    query SigmaRailBenchmarkPreferences {
      currentUser {
        id
        benchmarkPreferences
      }
    }
  `);
  let value = data.currentUser?.benchmarkPreferences;
  if (typeof value === "string") {
    try {
      value = JSON.parse(value);
    } catch {
      value = null;
    }
  }
  const preferences = Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string").map((item) => item.trim().toUpperCase()).filter(Boolean).slice(0, 6)
    : null;
  return { userId: data.currentUser?.id ?? null, preferences };
}

export async function saveBenchmarkPreferences(preferences: string[]): Promise<void> {
  await executeGraphQL(`
    mutation SaveSigmaRailBenchmarkPreferences($input: UpdateCurrentUserMutationInput!) {
      updateCurrentUser(input: $input) {
        userProfile {
          id
        }
      }
    }
  `, { input: { benchmarkPreferences: JSON.stringify(preferences) } });
}
