"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { updateProjectLink } from "../api/fetchers";
import { projectLinksKeys } from "../api/query-keys";
import { useToastMessage } from "@/shared/hooks/use-toast-message";

export function useUpdateProjectLink(projectId: string) {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("projects");

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: { name?: string; url?: string } }) =>
      updateProjectLink(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: projectLinksKeys.forProject(projectId) });
      success("linkUpdated");
    },
    onError: error,
  });
}
