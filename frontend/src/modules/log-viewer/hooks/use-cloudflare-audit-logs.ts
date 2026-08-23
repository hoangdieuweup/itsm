"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchCloudflareAuditLogsOrNull } from "../api/fetchers";
import { logViewerKeys } from "../api/query-keys";

/**
 * data is undefined while loading, null when the environment has no bound
 * Cloudflare zone, or the entry array once loaded.
 */
export function useCloudflareAuditLogsQuery(environmentId: string, params: { since?: string; before?: string }) {
  return useQuery({
    queryKey: logViewerKeys.cloudflareAuditLogs(environmentId, params.since, params.before),
    queryFn: () => fetchCloudflareAuditLogsOrNull(environmentId, params),
  });
}
