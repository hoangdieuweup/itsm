import { apiFetch } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";
import { cloudflareAccountSchema, type CloudflareAccount } from "../model/schema";

/**
 * Fetches every Cloudflare account visible to the current user from
 * GET /cloudflare-accounts (already filtered server-side).
 */
export async function fetchCloudflareAccounts(): Promise<CloudflareAccount[]> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.CLOUDFLARE_ACCOUNTS.ROOT);
  return cloudflareAccountSchema.array().parse(raw);
}

/**
 * Fetches one Cloudflare account from GET /cloudflare-accounts/{id}.
 */
export async function fetchCloudflareAccount(id: string): Promise<CloudflareAccount> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.CLOUDFLARE_ACCOUNTS.DETAIL(id));
  return cloudflareAccountSchema.parse(raw);
}
