"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createProjectRole } from "../api/fetchers";
import { projectRolesKeys } from "../api/query-keys";
import { useToastMessage } from "@/shared/hooks/use-toast-message";

export function useCreateProjectRole(projectId: string) {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("projects");

  return useMutation({
    mutationFn: (data: { name: string; permissionIds: string[] }) => createProjectRole(projectId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: projectRolesKeys.forProject(projectId) });
      success("projectRoleCreated");
    },
    onError: error,
  });
}
