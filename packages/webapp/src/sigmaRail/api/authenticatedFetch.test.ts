import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@sb/webapp-api-client/api";
import { authenticatedFetch } from "./authenticatedFetch";
import { setActiveTenantId } from "../lib/tenantRequest";

vi.mock("@sb/webapp-api-client/api", () => ({
  apiClient: { request: vi.fn() },
}));

const requestMock = vi.mocked(apiClient.request);

describe("authenticatedFetch", () => {
  beforeEach(() => {
    requestMock.mockReset();
    setActiveTenantId("tenant-global-id");
  });

  it("uses the AppTension client while preserving SigmaRail wire-case JSON", async () => {
    const payload = '{"SigmaRail":{"DataSources":[{"overall_score":1}]}}';
    requestMock.mockResolvedValue({
      data: payload,
      status: 200,
      statusText: "OK",
      headers: { "content-type": "application/json" },
    } as never);

    const response = await authenticatedFetch("/api/backtests/specs", {
      method: "POST",
      body: payload,
    });

    expect(requestMock).toHaveBeenCalledOnce();
    const config = requestMock.mock.calls[0]?.[0];
    expect(config?.url).toBe("/api/backtests/specs");
    expect(config?.method).toBe("POST");
    expect(config?.headers).toMatchObject({ "x-tenant-id": "tenant-global-id" });
    const requestTransformers = config?.transformRequest as Array<(data: unknown) => unknown> | undefined;
    const responseTransformers = config?.transformResponse as Array<(data: unknown) => unknown> | undefined;
    expect(requestTransformers?.[0](payload)).toBe(payload);
    expect(responseTransformers?.[0](payload)).toBe(payload);
    expect(await response.text()).toBe(payload);
  });

  it("returns error responses to existing Fetch-style handlers", async () => {
    requestMock.mockRejectedValue({
      response: {
        data: '{"detail":"Authentication credentials were not provided."}',
        status: 401,
        statusText: "Unauthorized",
        headers: { "content-type": "application/json" },
      },
    });

    const response = await authenticatedFetch("/api/screens/preview-ir");

    expect(response.status).toBe(401);
    await expect(response.json()).resolves.toEqual({
      detail: "Authentication credentials were not provided.",
    });
  });
});
