"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchCloudflareConfigOrNull } from "../api/fetchers";
import { cloudflareConfigKeys } from "../api/query-keys";

export function useCloudflareConfigQuery(environmentId: string) {
  return useQuery({
    queryKey: cloudflareConfigKeys.detail(environmentId),
    queryFn: () => fetchCloudflareConfigOrNull(environmentId),
  });
}
