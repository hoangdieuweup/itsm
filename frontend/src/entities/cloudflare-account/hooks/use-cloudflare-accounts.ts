"use client";

import { useSuspenseQuery } from "@tanstack/react-query";
import { fetchCloudflareAccount, fetchCloudflareAccounts } from "../api/fetchers";
import { cloudflareAccountsKeys } from "../api/query-keys";

export function useCloudflareAccountsQuery() {
  return useSuspenseQuery({
    queryKey: cloudflareAccountsKeys.list(),
    queryFn: () => fetchCloudflareAccounts(),
  });
}

export function useCloudflareAccountQuery(id: string) {
  return useSuspenseQuery({
    queryKey: cloudflareAccountsKeys.detail(id),
    queryFn: () => fetchCloudflareAccount(id),
  });
}
