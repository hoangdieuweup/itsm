"use client";

import { useSuspenseQuery } from "@tanstack/react-query";
import { fetchEnvironmentById, fetchProjectEnvironments } from "../api/fetchers";
import { environmentsKeys } from "../api/query-keys";

export function useProjectEnvironmentsQuery(projectId: string) {
  return useSuspenseQuery({
    queryKey: environmentsKeys.forProject(projectId),
    queryFn: () => fetchProjectEnvironments(projectId),
  });
}

export function useEnvironmentQuery(id: string) {
  return useSuspenseQuery({
    queryKey: environmentsKeys.detail(id),
    queryFn: () => fetchEnvironmentById(id),
  });
}
