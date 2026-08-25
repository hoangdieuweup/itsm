"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { assignMemberProjectRole } from "../api/fetchers";
import { projectMembersKeys } from "../api/query-keys";
import { projectPermissionsKeys } from "@/entities/permission";
import { useToastMessage } from "@/shared/hooks/use-toast-message";

/**
 * Invalidates both the member list AND the caller's own effective
 * permission set on success — assigning a role changes what that member
 * can do, and if the caller assigned their own role, their own gates
 * (CanInProject) must reflect it immediately, not after a stale-time wait.
 */
export function useAssignMemberProjectRole(projectId: string) {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("projects");

  return useMutation({
    mutationFn: ({ userId, projectRoleId }: { userId: string; projectRoleId: string | null }) =>
      assignMemberProjectRole(projectId, userId, projectRoleId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: projectMembersKeys.forProject(projectId) });
      queryClient.invalidateQueries({ queryKey: projectPermissionsKeys.forProject(projectId) });
      success("memberRoleAssigned");
    },
    onError: error,
  });
}
