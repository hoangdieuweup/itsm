import { apiFetch } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";
import { cloudflareConfigSchema, type CloudflareConfig } from "@/entities/cloudflare-config";
import {
  dnsRecordSchema,
  zoneOptionSchema,
  type DnsRecord,
  type DnsRecordType,
  type ZoneOption,
} from "../model/schema";

/**
 * Fetches every zone available on a Cloudflare account, for the bind-time
 * zone picker (GET /cloudflare-accounts/{accountId}/zones).
 */
export async function fetchZones(accountId: string): Promise<ZoneOption[]> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.CLOUDFLARE_DNS.ZONES(accountId));
  return zoneOptionSchema.array().parse(raw);
}

export async function createCloudflareConfig(data: {
  environmentId: string;
  cloudflareAccountId: string;
  zoneId: string;
}): Promise<CloudflareConfig> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.CLOUDFLARE_DNS.CONFIGS_ROOT, {
    method: "POST",
    data,
  });
  return cloudflareConfigSchema.parse(raw);
}

export async function updateCloudflareConfig(environmentId: string, zoneId: string): Promise<CloudflareConfig> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.CLOUDFLARE_DNS.CONFIG(environmentId), {
    method: "PATCH",
    data: { zoneId },
  });
  return cloudflareConfigSchema.parse(raw);
}

export async function deleteCloudflareConfig(environmentId: string): Promise<void> {
  await apiFetch<unknown>(API_CONFIG.ENDPOINTS.CLOUDFLARE_DNS.CONFIG(environmentId), { method: "DELETE" });
}

export async function fetchDnsRecords(environmentId: string): Promise<DnsRecord[]> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.CLOUDFLARE_DNS.RECORDS(environmentId));
  return dnsRecordSchema.array().parse(raw);
}

export interface DnsRecordFormValues {
  recordType: DnsRecordType;
  name: string;
  content: string;
  priority?: number | null;
  proxied: boolean;
  ttl: number;
}

/**
 * record_type and name are immutable after creation (matches the backend's
 * DnsRecordUpdate schema, which accepts neither) — changing either means
 * delete + recreate, not an update.
 */
export interface DnsRecordUpdateValues {
  content: string;
  priority?: number | null;
  proxied: boolean;
  ttl: number;
}

export async function createDnsRecord(environmentId: string, data: DnsRecordFormValues): Promise<DnsRecord> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.CLOUDFLARE_DNS.RECORDS(environmentId), {
    method: "POST",
    data,
  });
  return dnsRecordSchema.parse(raw);
}

export async function updateDnsRecord(
  environmentId: string,
  recordId: string,
  data: DnsRecordUpdateValues,
): Promise<DnsRecord> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.CLOUDFLARE_DNS.RECORD_DETAIL(environmentId, recordId), {
    method: "PATCH",
    data,
  });
  return dnsRecordSchema.parse(raw);
}

export async function deleteDnsRecord(environmentId: string, recordId: string): Promise<void> {
  await apiFetch<unknown>(API_CONFIG.ENDPOINTS.CLOUDFLARE_DNS.RECORD_DETAIL(environmentId, recordId), {
    method: "DELETE",
  });
}

export async function syncDnsRecords(environmentId: string): Promise<DnsRecord[]> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.CLOUDFLARE_DNS.SYNC(environmentId), {
    method: "POST",
  });
  return dnsRecordSchema.array().parse(raw);
}
