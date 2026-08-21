"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deleteProject } from "../api/fetchers";
import { projectsKeys } from "@/entities/project";

export function useDeleteProject() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => deleteProject(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: projectsKeys.all });
    },
  });
}
