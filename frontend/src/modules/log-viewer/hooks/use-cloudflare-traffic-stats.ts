"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchCloudflareTrafficStatsOrNull } from "../api/fetchers";
import { logViewerKeys } from "../api/query-keys";

/**
 * data is undefined while loading, null when the environment has no bound
 * Cloudflare zone, or the stats payload once loaded. A missing base_url
 * surfaces via the query's own `error` (see fetchCloudflareTrafficStatsOrNull).
 */
export function useCloudflareTrafficStatsQuery(environmentId: string, params: { since?: string; until?: string }) {
  return useQuery({
    queryKey: logViewerKeys.cloudflareTrafficStats(environmentId, params.since, params.until),
    queryFn: () => fetchCloudflareTrafficStatsOrNull(environmentId, params),
  });
}
