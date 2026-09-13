import { apiFetch } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";
import type { AccessLevel } from "@/shared/constants/cloudflare";
import { cloudflareAccountSchema, type CloudflareAccount } from "@/entities/cloudflare-account";
import {
  cloudflareAccountManagerSchema,
  revealedTokenSchema,
  type CloudflareAccountManager,
} from "../model/schema";

export async function createCloudflareAccount(data: {
  label: string;
  cfAccountId: string;
  apiToken: string;
}): Promise<CloudflareAccount> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.CLOUDFLARE_ACCOUNTS.ROOT, {
    method: "POST",
    data,
  });
  return cloudflareAccountSchema.parse(raw);
}

export async function updateCloudflareAccount(
  id: string,
  data: { label?: string; apiToken?: string },
): Promise<CloudflareAccount> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.CLOUDFLARE_ACCOUNTS.DETAIL(id), {
    method: "PATCH",
    data,
  });
  return cloudflareAccountSchema.parse(raw);
}

export async function deleteCloudflareAccount(id: string): Promise<void> {
  await apiFetch<null>(API_CONFIG.ENDPOINTS.CLOUDFLARE_ACCOUNTS.DETAIL(id), { method: "DELETE" });
}

export async function testCloudflareAccountConnection(id: string): Promise<void> {
  await apiFetch<null>(API_CONFIG.ENDPOINTS.CLOUDFLARE_ACCOUNTS.TEST_CONNECTION(id), { method: "POST" });
}

export async function revealCloudflareAccountToken(id: string): Promise<string> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.CLOUDFLARE_ACCOUNTS.REVEAL_TOKEN(id), {
    method: "POST",
  });
  return revealedTokenSchema.parse(raw).apiToken;
}

export async function fetchCloudflareAccountManagers(accountId: string): Promise<CloudflareAccountManager[]> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.CLOUDFLARE_ACCOUNTS.MANAGERS(accountId));
  return cloudflareAccountManagerSchema.array().parse(raw);
}

export async function assignCloudflareAccountManager(
  accountId: string,
  data: { userId: string; accessLevel: AccessLevel },
): Promise<void> {
  await apiFetch<null>(API_CONFIG.ENDPOINTS.CLOUDFLARE_ACCOUNTS.MANAGERS(accountId), {
    method: "POST",
    data,
  });
}

export async function updateCloudflareAccountManager(
  accountId: string,
  userId: string,
  data: { accessLevel: AccessLevel },
): Promise<void> {
  await apiFetch<null>(API_CONFIG.ENDPOINTS.CLOUDFLARE_ACCOUNTS.MANAGER_DETAIL(accountId, userId), {
    method: "PATCH",
    data,
  });
}

export async function removeCloudflareAccountManager(accountId: string, userId: string): Promise<void> {
  await apiFetch<null>(API_CONFIG.ENDPOINTS.CLOUDFLARE_ACCOUNTS.MANAGER_DETAIL(accountId, userId), {
    method: "DELETE",
  });
}
