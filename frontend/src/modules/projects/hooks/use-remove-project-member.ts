"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { removeProjectMember } from "../api/fetchers";
import { projectMembersKeys } from "../api/query-keys";
import { useToastMessage } from "@/shared/hooks/use-toast-message";

export function useRemoveProjectMember(projectId: string) {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("projects");

  return useMutation({
    mutationFn: (userId: string) => removeProjectMember(projectId, userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: projectMembersKeys.forProject(projectId) });
      success("memberRemoved");
    },
    onError: error,
  });
}
