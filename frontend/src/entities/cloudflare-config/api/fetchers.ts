import { apiFetch, ApiRequestError } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";
import { cloudflareConfigSchema, type CloudflareConfig } from "../model/schema";

/**
 * Fetches one environment's Cloudflare binding, or null if unbound
 * (GET returns 404 `cloudflare_config_not_found`, which this normalizes to
 * null rather than throwing — "not yet bound" is expected UI state, not an error).
 */
export async function fetchCloudflareConfigOrNull(environmentId: string): Promise<CloudflareConfig | null> {
  try {
    const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.CLOUDFLARE_DNS.CONFIG(environmentId));
    return cloudflareConfigSchema.parse(raw);
  } catch (error) {
    if (error instanceof ApiRequestError && error.code === "cloudflare_config_not_found") {
      return null;
    }
    throw error;
  }
}
