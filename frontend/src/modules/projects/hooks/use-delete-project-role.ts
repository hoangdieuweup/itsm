"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deleteProjectRole } from "../api/fetchers";
import { projectRolesKeys } from "../api/query-keys";
import { useToastMessage } from "@/shared/hooks/use-toast-message";

export function useDeleteProjectRole(projectId: string) {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("projects");

  return useMutation({
    mutationFn: (id: string) => deleteProjectRole(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: projectRolesKeys.forProject(projectId) });
      success("projectRoleDeleted");
    },
    onError: error,
  });
}
