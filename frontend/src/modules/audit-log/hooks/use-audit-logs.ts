"use client";

import { useSuspenseQuery } from "@tanstack/react-query";
import { fetchAuditLogs, type AuditLogFilters } from "../api/fetchers";
import { auditLogsKeys } from "../api/query-keys";

export function useAuditLogsQuery(filters: AuditLogFilters = {}) {
  return useSuspenseQuery({
    queryKey: auditLogsKeys.list(filters as Record<string, string | number | undefined>),
    queryFn: () => fetchAuditLogs(filters),
  });
}
