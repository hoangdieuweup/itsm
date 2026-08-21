"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createProject } from "../api/fetchers";
import { projectsKeys } from "@/entities/project";

export function useCreateProject() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ name, description }: { name: string; description?: string }) =>
      createProject(name, description),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: projectsKeys.all });
    },
  });
}
