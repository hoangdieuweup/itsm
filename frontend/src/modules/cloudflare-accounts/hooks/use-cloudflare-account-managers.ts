"use client";

import { useSuspenseQuery } from "@tanstack/react-query";
import { fetchCloudflareAccountManagers } from "../api/fetchers";

export const cloudflareAccountManagersKeys = {
  forAccount: (accountId: string) => ["cloudflare-accounts", "managers", accountId] as const,
};

export function useCloudflareAccountManagersQuery(accountId: string) {
  return useSuspenseQuery({
    queryKey: cloudflareAccountManagersKeys.forAccount(accountId),
    queryFn: () => fetchCloudflareAccountManagers(accountId),
  });
}
