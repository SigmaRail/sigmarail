import { apiClient } from "@sb/webapp-api-client/api";
import { tenantRequestHeaders } from "../lib/tenantRequest";

type FetchLikeResponse = {
  data?: unknown;
  headers?: Record<string, unknown>;
  status: number;
  statusText?: string;
};

function toResponse(result: FetchLikeResponse): Response {
  const headers = new Headers();
  for (const [name, value] of Object.entries(result.headers ?? {})) {
    if (typeof value === "string") headers.set(name, value);
  }

  const body = result.data == null
    ? null
    : typeof result.data === "string"
      ? result.data
      : JSON.stringify(result.data);

  return new Response([204, 205, 304].includes(result.status) ? null : body, {
    status: result.status,
    statusText: result.statusText,
    headers,
  });
}

/**
 * Keep the workbench's Fetch-style REST API while using AppTension's shared
 * client for bearer tokens, cookie credentials, and refresh-on-401 behavior.
 * Per-request transformers preserve SigmaRail's versioned wire keys verbatim.
 */
export async function authenticatedFetch(
  input: string | URL,
  init: Pick<RequestInit, "body" | "headers" | "method" | "signal"> = {},
): Promise<Response> {
  const headers = tenantRequestHeaders(init.headers);
  if (!headers.has("Accept")) headers.set("Accept", "application/json");
  if (init.body != null && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const config = {
    url: String(input),
    method: init.method ?? "GET",
    data: init.body,
    headers: Object.fromEntries(headers.entries()),
    signal: init.signal ?? undefined,
    responseType: "text" as const,
    transformRequest: [(data: unknown) => data],
    transformResponse: [(data: unknown) => data],
  };

  try {
    const result = await apiClient.request<string>(config);
    return toResponse(result);
  } catch (error) {
    if (error && typeof error === "object" && "response" in error) {
      const response = (error as { response?: FetchLikeResponse }).response;
      if (response && typeof response.status === "number") return toResponse(response);
    }
    throw error;
  }
}
