"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { updateEnvironment } from "../api/fetchers";
import { environmentsKeys } from "@/entities/environment";
import { useToastMessage } from "@/shared/hooks/use-toast-message";

export function useUpdateEnvironment(projectId: string) {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("projects");

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: { name?: string; baseUrl?: string } }) =>
      updateEnvironment(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: environmentsKeys.forProject(projectId) });
      success("environmentUpdated");
    },
    onError: error,
  });
}
