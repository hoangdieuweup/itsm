"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createEnvironment } from "../api/fetchers";
import { environmentsKeys } from "@/entities/environment";

export function useCreateEnvironment(projectId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: { type: string; name: string; baseUrl?: string }) =>
      createEnvironment(projectId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: environmentsKeys.forProject(projectId) });
    },
  });
}
