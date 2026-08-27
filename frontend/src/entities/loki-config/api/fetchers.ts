import { apiFetch, ApiRequestError } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";
import { lokiConfigSchema, type LokiConfig } from "../model/schema";

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
