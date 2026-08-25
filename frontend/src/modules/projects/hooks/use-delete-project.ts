"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deleteProject } from "../api/fetchers";
import { projectsKeys } from "@/entities/project";
import { useToastMessage } from "@/shared/hooks/use-toast-message";

export function useDeleteProject() {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("projects");

  return useMutation({
    mutationFn: (id: string) => deleteProject(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: projectsKeys.all });
      success("projectDeleted");
    },
    onError: error,
  });
}
