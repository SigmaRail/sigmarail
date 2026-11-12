import type {
  LiveDeploymentStatus,
  LiveDeploymentSummary,
  PromotionGateResult,
  RegisterPaperDeploymentResponse,
  LiveAccountProfile,
  LiveAccountVerification,
  LiveBrokerageCatalog,
  LocalLiveRuntime,
  LocalRuntimeActionResponse,
} from "../types";

async function parseJson(res: Response): Promise<unknown> {
  const text = await res.text();
  if (!text) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    throw new Error(`Invalid JSON from ${res.url}`);
  }
}

function unwrapData(payload: unknown): unknown {
  if (payload && typeof payload === "object") {
    const obj = payload as Record<string, unknown>;
    if ("data" in obj && obj.data !== undefined) return obj.data;
    if ("result" in obj && obj.result !== undefined) return obj.result;
  }
  return payload;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
    ...init,
  });
  const raw = await parseJson(res);
  if (!res.ok) {
    const detail =
      raw && typeof raw === "object" && "detail" in raw
        ? String((raw as { detail: unknown }).detail)
        : raw && typeof raw === "object" && "error" in raw
          ? String((raw as { error: unknown }).error)
          : res.statusText;
    throw new Error(detail || `HTTP ${res.status}`);
  }
  return unwrapData(raw) as T;
}

export async function fetchLiveDeployments(
  limit = 20,
): Promise<LiveDeploymentSummary[]> {
  const data = await request<{ deployments: LiveDeploymentSummary[] }>(
    `/api/live/deployments?limit=${limit}`,
  );
  return Array.isArray(data?.deployments) ? data.deployments : [];
}

export async function registerPaperDeployment(body: {
  ir_id: string;
  approval_backtest_run_id: string;
  deployment_id?: string;
}): Promise<RegisterPaperDeploymentResponse> {
  return request<RegisterPaperDeploymentResponse>("/api/live/deployments", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function fetchLiveDeploymentStatus(
  deploymentId: string,
): Promise<LiveDeploymentStatus> {
  return request<LiveDeploymentStatus>(
    `/api/live/deployments/${encodeURIComponent(deploymentId)}/status`,
  );
}

export async function fetchPromotionGate(
  irId: string,
  approvalBacktestRunId: string,
): Promise<PromotionGateResult> {
  const params = new URLSearchParams({
    ir_id: irId,
    approval_backtest_run_id: approvalBacktestRunId,
  });
  return request<PromotionGateResult>(`/api/live/promotion-gate?${params.toString()}`);
}

export async function fetchLiveAccountProfiles(): Promise<LiveAccountProfile[]> {
  const data = await request<{ profiles: LiveAccountProfile[] }>("/api/live/accounts");
  return Array.isArray(data?.profiles) ? data.profiles : [];
}

export async function fetchLiveBrokerages(): Promise<LiveBrokerageCatalog> {
  const data = await request<LiveBrokerageCatalog>("/api/live/brokerages");
  return {
    brokerages: Array.isArray(data?.brokerages) ? data.brokerages : [],
    data_providers: Array.isArray(data?.data_providers) ? data.data_providers : [],
  };
}

export async function saveLiveAccountProfile(body: {
  id?: string;
  provider: string;
  data_provider: string;
  environment: "paper" | "live";
  display_name: string;
  account_identifier?: string;
  credentials?: Record<string, string>;
}): Promise<LiveAccountProfile> {
  return request<LiveAccountProfile>("/api/live/accounts", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function verifyLiveAccountProfile(profileId: string): Promise<LiveAccountVerification> {
  return request<LiveAccountVerification>(`/api/live/accounts/${encodeURIComponent(profileId)}/verify`, {
    method: "POST",
  });
}

export async function setLiveAccountProfileActive(profileId: string, active: boolean): Promise<LiveAccountProfile> {
  return request<LiveAccountProfile>(`/api/live/accounts/${encodeURIComponent(profileId)}`, {
    method: "PATCH",
    body: JSON.stringify({ active }),
  });
}

export async function deleteLiveAccountProfile(profileId: string): Promise<void> {
  await request<void>(`/api/live/accounts/${encodeURIComponent(profileId)}`, { method: "DELETE" });
}

export async function fetchLocalLiveRuntime(): Promise<LocalLiveRuntime> {
  return request<LocalLiveRuntime>("/api/live/local-runtime");
}

export async function controlLocalLiveRuntime(body:
  | { action: "start-paper" | "start-live"; ir_id: string; approval_backtest_run_id: string; account_profile_id: string; live_confirmation?: string }
  | { action: "stop" | "liquidate"; deployment_id: string; confirmation?: string }
): Promise<LocalRuntimeActionResponse> {
  return request<LocalRuntimeActionResponse>("/api/live/local-runtime", {
    method: "POST",
    body: JSON.stringify(body),
  });
}
