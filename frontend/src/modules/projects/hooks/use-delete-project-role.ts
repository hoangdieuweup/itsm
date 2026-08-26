"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deleteProjectRole } from "../api/fetchers";
import { projectRolesKeys } from "../api/query-keys";
import { projectPermissionsKeys } from "@/entities/permission";
import { useToastMessage } from "@/shared/hooks/use-toast-message";

/**
 * Invalidates the role list AND the caller's own effective permission set —
 * deleting a role degrades every member holding it back to global-only
 * permissions (ON DELETE SET NULL), including the caller if they held it.
 */
export function useDeleteProjectRole(projectId: string) {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("projects");

  return useMutation({
    mutationFn: (id: string) => deleteProjectRole(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: projectRolesKeys.forProject(projectId) });
      queryClient.invalidateQueries({ queryKey: projectPermissionsKeys.forProject(projectId) });
      success("projectRoleDeleted");
    },
    onError: error,
  });
}
