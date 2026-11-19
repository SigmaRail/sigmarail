import { beforeEach, describe, expect, it, vi } from "vitest";
import { authenticatedFetch } from "./authenticatedFetch";
import { fetchSavedScreens, fetchTemplates } from "./screens";

vi.mock("./authenticatedFetch", () => ({
  authenticatedFetch: vi.fn(),
}));

const authenticatedFetchMock = vi.mocked(authenticatedFetch);

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("screen catalog responses", () => {
  beforeEach(() => authenticatedFetchMock.mockReset());

  it("preserves valid partial saved-screen catalogs", async () => {
    authenticatedFetchMock.mockResolvedValue(
      jsonResponse({
        screens: [],
        shared_catalog_available: false,
        shared_catalog_warning: "Shared templates are temporarily unavailable.",
      }),
    );

    await expect(fetchSavedScreens()).resolves.toMatchObject({
      screens: [],
      shared_catalog_available: false,
      shared_catalog_warning: "Shared templates are temporarily unavailable.",
    });
  });

  it("rejects malformed saved-screen responses instead of treating them as empty", async () => {
    authenticatedFetchMock.mockResolvedValue(jsonResponse({ result: [] }));

    await expect(fetchSavedScreens()).rejects.toThrow(
      "Saved screen catalog returned an invalid response.",
    );
  });

  it("rejects malformed built-in template responses instead of treating them as empty", async () => {
    authenticatedFetchMock.mockResolvedValue(jsonResponse({ templates: null }));

    await expect(fetchTemplates()).rejects.toThrow(
      "Screen template catalog returned an invalid response.",
    );
  });
});
