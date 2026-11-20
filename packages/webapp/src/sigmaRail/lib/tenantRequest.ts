let activeTenantId: string | null = null;

export function setActiveTenantId(tenantId: string | null) {
  activeTenantId = tenantId;
}

export function tenantRequestHeaders(headers?: HeadersInit): Headers {
  const result = new Headers(headers);
  if (activeTenantId) result.set("X-Tenant-ID", activeTenantId);
  return result;
}
