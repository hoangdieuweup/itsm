"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { addProjectMember } from "../api/fetchers";
import { projectMembersKeys } from "../api/query-keys";
import { useToastMessage } from "@/shared/hooks/use-toast-message";

export function useAddProjectMember(projectId: string) {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("projects");

  return useMutation({
    mutationFn: (userId: string) => addProjectMember(projectId, userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: projectMembersKeys.forProject(projectId) });
      success("memberAdded");
    },
    onError: error,
  });
}
