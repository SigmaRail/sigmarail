/** API client for strategy pipeline endpoints (/api/strategy/*). */

import {
  omitEmptyDocumentation,
  type FactorInfo,
  type PipelineDocument,
  type StrategyPreset,
} from "../components/strategy/StrategyDocument";
import type {
  CatalogTemplateKind,
  CatalogTemplateStatus,
  ScreenTemplateSummary,
} from "../types";

export type CatalogTemplateDetail = ScreenTemplateSummary & {
  title?: string;
  body?: PipelineDocument | Record<string, unknown>;
  spec?: Record<string, unknown>;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Request failed ${res.status}: ${text}`);
  }
  return (await res.json()) as T;
}

export async function fetchStrategyFactors(): Promise<Record<string, FactorInfo>> {
  const data = await request<{ factors: Record<string, FactorInfo> }>("/api/strategy/factors");
  return data.factors ?? {};
}

export async function fetchStrategyPresets(): Promise<StrategyPreset[]> {
  const data = await request<{ presets: StrategyPreset[] }>("/api/strategy/presets");
  return Array.isArray(data.presets) ? data.presets : [];
}

export async function fetchStrategyPreset(presetId: string): Promise<PipelineDocument> {
  return request<PipelineDocument>(`/api/strategy/presets/${encodeURIComponent(presetId)}`);
}

export async function fetchCatalogTemplates(opts?: {
  kind?: CatalogTemplateKind;
  status?: CatalogTemplateStatus;
}): Promise<ScreenTemplateSummary[]> {
  const params = new URLSearchParams();
  if (opts?.kind) params.set("kind", opts.kind);
  if (opts?.status) params.set("status", opts.status);
  const qs = params.toString();
  const data = await request<{ templates?: ScreenTemplateSummary[] }>(
    `/api/templates${qs ? `?${qs}` : ""}`,
  );
  return Array.isArray(data.templates) ? data.templates : [];
}

export async function fetchCatalogTemplate(id: string): Promise<CatalogTemplateDetail> {
  return request<CatalogTemplateDetail>(`/api/templates/${encodeURIComponent(id)}`);
}

export async function compilePipeline(doc: PipelineDocument): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>("/api/strategy/pipelines/compile", {
    method: "POST",
    body: JSON.stringify(omitEmptyDocumentation(doc)),
  });
}

export async function decompilePipeline(spec: Record<string, unknown>): Promise<PipelineDocument> {
  return request<PipelineDocument>("/api/strategy/pipelines/decompile", {
    method: "POST",
    body: JSON.stringify(spec),
  });
}

export async function validatePipeline(doc: PipelineDocument): Promise<{ valid: boolean; error?: string }> {
  return request<{ valid: boolean; error?: string }>("/api/strategy/pipelines/validate", {
    method: "POST",
    body: JSON.stringify(doc),
  });
}

export async function compilePortfolio(doc: Record<string, unknown>): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>("/api/strategy/pipelines/compile-portfolio", {
    method: "POST",
    body: JSON.stringify(doc),
  });
}

export async function decompilePortfolio(spec: Record<string, unknown>): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>("/api/strategy/pipelines/decompile-portfolio", {
    method: "POST",
    body: JSON.stringify(spec),
  });
}
