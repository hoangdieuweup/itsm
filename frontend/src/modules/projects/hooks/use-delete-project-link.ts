"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deleteProjectLink } from "../api/fetchers";
import { projectLinksKeys } from "../api/query-keys";
import { useToastMessage } from "@/shared/hooks/use-toast-message";

export function useDeleteProjectLink(projectId: string) {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("projects");

  return useMutation({
    mutationFn: (id: string) => deleteProjectLink(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: projectLinksKeys.forProject(projectId) });
      success("linkDeleted");
    },
    onError: error,
  });
}
