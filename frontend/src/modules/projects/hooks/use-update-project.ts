"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { updateProject } from "../api/fetchers";
import { projectsKeys } from "@/entities/project";

export function useUpdateProject() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: string;
      data: { name?: string; description?: string };
    }) => updateProject(id, data),
    onSuccess: (_result, variables) => {
      queryClient.invalidateQueries({ queryKey: projectsKeys.all });
      queryClient.invalidateQueries({ queryKey: projectsKeys.detail(variables.id) });
    },
  });
}
