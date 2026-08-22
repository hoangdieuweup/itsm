"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { updateProjectLink } from "../api/fetchers";
import { projectLinksKeys } from "../api/query-keys";

export function useUpdateProjectLink(projectId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: { name?: string; url?: string } }) =>
      updateProjectLink(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: projectLinksKeys.forProject(projectId) });
    },
  });
}
