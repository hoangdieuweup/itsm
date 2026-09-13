"use client";

import { useQuery } from "@tanstack/react-query";
import { runLogQuery, type LogQueryValues } from "../api/fetchers";
import { logViewerKeys } from "../api/query-keys";

/**
 * Declarative TanStack Query hook for reading Loki logs.
 * Executes automatically on mount when enabled, and refetches when params change.
 */
export function useLogQuery(
  environmentId: string,
  params: LogQueryValues,
  options?: { enabled?: boolean },
) {
  return useQuery({
    queryKey: logViewerKeys.query(environmentId, params),
    queryFn: () => runLogQuery(environmentId, params),
    enabled: options?.enabled ?? Boolean(params.query),
    staleTime: 10_000,
  });
}
