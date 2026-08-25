"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createProject } from "../api/fetchers";
import { projectsKeys } from "@/entities/project";
import { useToastMessage } from "@/shared/hooks/use-toast-message";

export function useCreateProject() {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("projects");

  return useMutation({
    mutationFn: ({ name, description }: { name: string; description?: string }) =>
      createProject(name, description),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: projectsKeys.all });
      success("projectCreated");
    },
    onError: error,
  });
}
