"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchCloudflareAuditLogs } from "../api/fetchers";
import { logViewerKeys } from "../api/query-keys";

export function useCloudflareAuditLogsQuery(
  environmentId: string,
  params: { since?: string; before?: string },
  enabled: boolean,
) {
  return useQuery({
    queryKey: logViewerKeys.cloudflareAuditLogs(environmentId, params.since, params.before),
    queryFn: () => fetchCloudflareAuditLogs(environmentId, params),
    enabled,
  });
}
