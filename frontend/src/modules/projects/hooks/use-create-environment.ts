"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createEnvironment } from "../api/fetchers";
import { environmentsKeys } from "@/entities/environment";
import { useToastMessage } from "@/shared/hooks/use-toast-message";

export function useCreateEnvironment(projectId: string) {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("projects");

  return useMutation({
    mutationFn: (data: { type: string; name: string; baseUrl?: string }) =>
      createEnvironment(projectId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: environmentsKeys.forProject(projectId) });
      success("environmentCreated");
    },
    onError: error,
  });
}
