"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { updateProjectRole } from "../api/fetchers";
import { projectRolesKeys } from "../api/query-keys";
import { useToastMessage } from "@/shared/hooks/use-toast-message";

export function useUpdateProjectRole(projectId: string) {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("projects");

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: { name?: string; permissionIds?: string[] } }) =>
      updateProjectRole(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: projectRolesKeys.forProject(projectId) });
      success("projectRoleUpdated");
    },
    onError: error,
  });
}
