"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deleteProjectLink } from "../api/fetchers";

export function useDeleteProjectLink(projectId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => deleteProjectLink(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects", "links", projectId] });
    },
  });
}
