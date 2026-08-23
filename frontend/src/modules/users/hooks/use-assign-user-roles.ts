"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { assignUserRoles } from "../api/fetchers";
import { usersKeys } from "@/entities/user";
import { rolesKeys } from "@/entities/role";
import { authKeys } from "@/entities/auth";

export function useAssignUserRoles() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ userId, roleIds }: { userId: string; roleIds: string[] }) =>
      assignUserRoles(userId, roleIds),
    onSuccess: (_, { userId }) => {
      queryClient.invalidateQueries({ queryKey: rolesKeys.userRoles(userId) });
      queryClient.invalidateQueries({ queryKey: rolesKeys.all });
      queryClient.invalidateQueries({ queryKey: usersKeys.all });
      queryClient.invalidateQueries({ queryKey: authKeys.session() });
    },
  });
}
