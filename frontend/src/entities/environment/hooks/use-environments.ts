"use client";

import { useSuspenseQuery } from "@tanstack/react-query";
import { fetchProjectEnvironments } from "../api/fetchers";
import { environmentsKeys } from "../api/query-keys";

export function useProjectEnvironmentsQuery(projectId: string) {
  return useSuspenseQuery({
    queryKey: environmentsKeys.forProject(projectId),
    queryFn: () => fetchProjectEnvironments(projectId),
  });
}
