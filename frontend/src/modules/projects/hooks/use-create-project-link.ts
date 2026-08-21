"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createProjectLink } from "../api/fetchers";

export function useCreateProjectLink(projectId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: { type: string; name: string; url: string }) =>
      createProjectLink(projectId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects", "links", projectId] });
    },
  });
}
