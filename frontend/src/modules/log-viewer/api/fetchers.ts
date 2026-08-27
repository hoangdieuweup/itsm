import { apiFetch, ApiRequestError } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";
import { lokiConfigSchema, type LokiAuthType, type LokiConfig } from "@/entities/loki-config";
import {
  cloudflareTrafficStatsSchema,
  logQueryResultSchema,
  type CloudflareTrafficStats,
  type LogEntry,
} from "../model/schema";

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
 * Fetches aggregated Cloudflare traffic stats (GraphQL Analytics —
 * Free-plan compatible substitute for Logpull/Logpush, which are
 * Enterprise-only) for the environment's own hostname. Returns null only
 * when the environment has no Cloudflare zone bound (404
 * `cloudflare_config_not_found`), same OrNull convention as elsewhere in this
 * module (e.g. fetchLokiConfigOrNull). A missing `base_url` (422
 * `cloudflare_environment_base_url_not_configured`) is left to propagate as
 * a normal query error instead, since it's a distinct, actionable state
 * ("configure this environment's base URL") rather than "nothing to show."
 */
export async function fetchCloudflareTrafficStatsOrNull(
  environmentId: string,
  params: { since?: string; until?: string },
): Promise<CloudflareTrafficStats | null> {
  try {
    const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.CLOUDFLARE_TRAFFIC_STATS.ROOT(environmentId), {
      params,
    });
    return cloudflareTrafficStatsSchema.parse(raw);
  } catch (error) {
    if (error instanceof ApiRequestError && error.code === "cloudflare_config_not_found") {
      return null;
    }
    throw error;
  }
}
