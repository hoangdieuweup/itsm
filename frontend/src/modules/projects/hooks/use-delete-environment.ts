"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deleteEnvironment } from "../api/fetchers";
import { environmentsKeys } from "@/entities/environment";

export function useDeleteEnvironment(projectId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => deleteEnvironment(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: environmentsKeys.forProject(projectId) });
    },
  });
}
