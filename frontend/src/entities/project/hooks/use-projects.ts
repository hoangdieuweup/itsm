"use client";

import { useSuspenseQuery } from "@tanstack/react-query";
import { fetchProject, fetchProjects } from "../api/fetchers";
import { projectsKeys } from "../api/query-keys";

export function useProjectsQuery(limit = 50, offset = 0) {
  return useSuspenseQuery({
    queryKey: projectsKeys.list({ limit, offset }),
    queryFn: () => fetchProjects(limit, offset),
  });
}

export function useProjectQuery(id: string) {
  return useSuspenseQuery({
    queryKey: projectsKeys.detail(id),
    queryFn: () => fetchProject(id),
  });
}
