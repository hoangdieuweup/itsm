"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createProjectLink } from "../api/fetchers";
import { projectLinksKeys } from "../api/query-keys";

export function useCreateProjectLink(projectId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: { type: string; name: string; url: string }) =>
      createProjectLink(projectId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: projectLinksKeys.forProject(projectId) });
    },
  });
}
