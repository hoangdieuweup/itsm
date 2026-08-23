"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchZones } from "../api/fetchers";
import { cloudflareDnsKeys } from "../api/query-keys";

export function useZonesQuery(accountId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: cloudflareDnsKeys.zones(accountId ?? "none"),
    queryFn: () => fetchZones(accountId as string),
    enabled: enabled && accountId !== null,
  });
}
