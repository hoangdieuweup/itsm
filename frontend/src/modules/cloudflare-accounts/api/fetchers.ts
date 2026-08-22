import { apiFetch } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";
import type { CloudflareAccount } from "@/entities/cloudflare-account";

export async function createCloudflareAccount(data: {
  label: string;
  cfAccountId: string;
  apiToken: string;
}): Promise<CloudflareAccount> {
  return apiFetch<CloudflareAccount>(API_CONFIG.ENDPOINTS.CLOUDFLARE_ACCOUNTS.ROOT, {
    method: "POST",
    data,
  });
}

export async function updateCloudflareAccount(
  id: string,
  data: { label?: string; apiToken?: string },
): Promise<CloudflareAccount> {
  return apiFetch<CloudflareAccount>(API_CONFIG.ENDPOINTS.CLOUDFLARE_ACCOUNTS.DETAIL(id), {
    method: "PATCH",
    data,
  });
}

export async function deleteCloudflareAccount(id: string): Promise<void> {
  await apiFetch<null>(API_CONFIG.ENDPOINTS.CLOUDFLARE_ACCOUNTS.DETAIL(id), { method: "DELETE" });
}

export async function testCloudflareAccountConnection(id: string): Promise<void> {
  await apiFetch<null>(API_CONFIG.ENDPOINTS.CLOUDFLARE_ACCOUNTS.TEST_CONNECTION(id), { method: "POST" });
}

export async function revealCloudflareAccountToken(id: string): Promise<string> {
  const result = await apiFetch<{ apiToken: string }>(
    API_CONFIG.ENDPOINTS.CLOUDFLARE_ACCOUNTS.REVEAL_TOKEN(id),
    { method: "POST" },
  );
  return result.apiToken;
}

export type AccessLevel = "owner" | "editor" | "viewer";

export interface CloudflareAccountManager {
  userId: string;
  email: string;
  name: string;
  accessLevel: AccessLevel;
  createdAt: string;
}

export async function fetchCloudflareAccountManagers(accountId: string): Promise<CloudflareAccountManager[]> {
  return apiFetch<CloudflareAccountManager[]>(API_CONFIG.ENDPOINTS.CLOUDFLARE_ACCOUNTS.MANAGERS(accountId));
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
