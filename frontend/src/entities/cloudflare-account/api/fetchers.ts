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

/**
 * Fetches all tunnels for a Cloudflare account — live API proxy.
 */
export async function fetchAccountTunnels(accountId: string): Promise<CfTunnel[]> {
  return apiFetch<CfTunnel[]>(API_CONFIG.ENDPOINTS.CLOUDFLARE_ACCOUNTS.TUNNELS(accountId));
}

/**
 * Fetches all zones for a Cloudflare account.
 */
export async function fetchAccountZones(accountId: string): Promise<CfZone[]> {
  return apiFetch<CfZone[]>(API_CONFIG.ENDPOINTS.CLOUDFLARE_DNS.ZONES(accountId));
}

/**
 * Fetches DNS records for a specific zone on a Cloudflare account.
 */
export async function fetchAccountZoneDnsRecords(accountId: string, zoneId: string): Promise<CfDnsRecord[]> {
  return apiFetch<CfDnsRecord[]>(API_CONFIG.ENDPOINTS.CLOUDFLARE_ACCOUNTS.ZONE_DNS_RECORDS(accountId, zoneId));
}

/* ── Lightweight types for Cloudflare API proxy responses ── */

export interface CfTunnelConnection {
  id: string;
  client_id?: string;
  client_version?: string;
  colo_name?: string;
  origin_ip?: string;
  opened_at?: string;
}

export interface CfTunnel {
  id: string;
  name: string;
  status: "inactive" | "degraded" | "healthy" | "down";
  tun_type?: string;
  config_src?: "local" | "cloudflare";
  created_at?: string;
  deleted_at?: string | null;
  conns_active_at?: string | null;
  conns_inactive_at?: string | null;
  connections?: CfTunnelConnection[];
}

export interface CfZone {
  id: string;
  name: string;
}

export interface CfDnsRecord {
  id: string;
  type: string;
  name: string;
  content: string;
  ttl: number;
  proxied: boolean;
  proxiable: boolean;
  comment?: string | null;
  tags?: string[];
  created_on?: string;
  modified_on?: string;
}
