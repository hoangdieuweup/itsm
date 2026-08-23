import { apiFetch, ApiRequestError } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";
import {
  cloudflareAuditLogEntrySchema,
  lokiConfigSchema,
  logQueryResultSchema,
  type CloudflareAuditLogEntry,
  type LogEntry,
  type LokiAuthType,
  type LokiConfig,
} from "../model/schema";

/**
 * Fetches one environment's Loki config, or null if unconfigured (GET
 * returns 404 `loki_config_not_found`, normalized to null — "not yet
 * configured" is expected UI state, not an error).
 */
export async function fetchLokiConfigOrNull(environmentId: string): Promise<LokiConfig | null> {
  try {
    const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.OBSERVABILITY.LOKI_CONFIG(environmentId));
    return lokiConfigSchema.parse(raw);
  } catch (error) {
    if (error instanceof ApiRequestError && error.code === "loki_config_not_found") {
      return null;
    }
    throw error;
  }
}

export interface LokiConfigFormValues {
  endpointUrl: string;
  tenantId: string | null;
  authType: LokiAuthType;
  credential: string | null;
  defaultQuery: string;
  defaultRangeMinutes: number;
}

export async function createLokiConfig(environmentId: string, data: LokiConfigFormValues): Promise<LokiConfig> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.OBSERVABILITY.LOKI_CONFIG(environmentId), {
    method: "POST",
    data,
  });
  return lokiConfigSchema.parse(raw);
}

export async function updateLokiConfig(
  environmentId: string,
  data: Partial<LokiConfigFormValues>,
): Promise<LokiConfig> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.OBSERVABILITY.LOKI_CONFIG(environmentId), {
    method: "PATCH",
    data,
  });
  return lokiConfigSchema.parse(raw);
}

export async function deleteLokiConfig(environmentId: string): Promise<void> {
  await apiFetch<unknown>(API_CONFIG.ENDPOINTS.OBSERVABILITY.LOKI_CONFIG(environmentId), { method: "DELETE" });
}

export interface LogQueryValues {
  query: string;
  start: string;
  end: string;
  limit?: number;
}

export async function runLogQuery(environmentId: string, data: LogQueryValues): Promise<LogEntry[]> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.OBSERVABILITY.LOKI_QUERY(environmentId), {
    method: "POST",
    data,
  });
  return logQueryResultSchema.parse(raw).entries;
}

/**
 * Fetches an environment's Cloudflare Audit Log entries, or null if the
 * environment has no Cloudflare zone bound (GET returns 404
 * `cloudflare_config_not_found`, normalized to null — same OrNull pattern
 * as fetchLokiConfigOrNull). Deliberately does NOT reach into
 * modules/cloudflare-dns for a separate "is bound" check — that would be a
 * forbidden module-to-module import; this endpoint's own 404 already tells
 * us everything we need.
 */
export async function fetchCloudflareAuditLogsOrNull(
  environmentId: string,
  params: { since?: string; before?: string },
): Promise<CloudflareAuditLogEntry[] | null> {
  try {
    const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.CLOUDFLARE_AUDIT_LOGS.ROOT(environmentId), {
      params,
    });
    return cloudflareAuditLogEntrySchema.array().parse(raw);
  } catch (error) {
    if (error instanceof ApiRequestError && error.code === "cloudflare_config_not_found") {
      return null;
    }
    throw error;
  }
}
