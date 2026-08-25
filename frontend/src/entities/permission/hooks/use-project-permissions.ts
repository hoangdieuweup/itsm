"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchProjectPermissions } from "../api/fetchers";
import { projectPermissionsKeys } from "../api/query-keys";

/**
 * Plain useQuery, NOT Suspense — ProjectPermissionProvider needs a
 * non-suspending pending state to implement its global-set fallback (D8).
 */
export function useProjectPermissionsQuery(projectId: string) {
  return useQuery({
    queryKey: projectPermissionsKeys.forProject(projectId),
    queryFn: () => fetchProjectPermissions(projectId),
    staleTime: 10_000,
  });
}
