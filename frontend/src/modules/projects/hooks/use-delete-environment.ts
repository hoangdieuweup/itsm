"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deleteEnvironment } from "../api/fetchers";
import { environmentsKeys } from "@/entities/environment";
import { useToastMessage } from "@/shared/hooks/use-toast-message";

export function useDeleteEnvironment(projectId: string) {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("projects");

  return useMutation({
    mutationFn: (id: string) => deleteEnvironment(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: environmentsKeys.forProject(projectId) });
      success("environmentDeleted");
    },
    onError: error,
  });
}
