"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { removeProjectMember } from "../api/fetchers";
import { projectMembersKeys } from "../api/query-keys";
import { projectPermissionsKeys } from "@/entities/permission";
import { useToastMessage } from "@/shared/hooks/use-toast-message";

/**
 * Invalidates the member list AND the caller's own effective permission
 * set — removing a member drops their project_members row entirely, which
 * matters if the caller removed themselves (falls back to no access at
 * all, unless they hold project:manage_all).
 */
export function useRemoveProjectMember(projectId: string) {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("projects");

  return useMutation({
    mutationFn: (userId: string) => removeProjectMember(projectId, userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: projectMembersKeys.forProject(projectId) });
      queryClient.invalidateQueries({ queryKey: projectPermissionsKeys.forProject(projectId) });
      success("memberRemoved");
    },
    onError: error,
  });
}
