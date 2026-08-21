"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { assignUserRoles } from "../api/fetchers";
import { rolesKeys } from "../api/query-keys";

export function useAssignUserRoles() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      userId,
      roleIds,
    }: {
      userId: string;
      roleIds: string[];
    }) => assignUserRoles(userId, roleIds),
    onSuccess: (_, { userId }) => {
      queryClient.invalidateQueries({ queryKey: rolesKeys.userRoles(userId) });
      queryClient.invalidateQueries({ queryKey: rolesKeys.all });
      queryClient.invalidateQueries({ queryKey: ["users"] });
      queryClient.invalidateQueries({ queryKey: ["auth", "session"] });
    },
  });
}
