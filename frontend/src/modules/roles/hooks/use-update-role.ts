"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { updateRole } from "../api/fetchers";
import { rolesKeys } from "../api/query-keys";

export function useUpdateRole() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      roleId,
      name,
      permissionIds,
    }: {
      roleId: number;
      name?: string;
      permissionIds?: number[];
    }) => updateRole(roleId, { name, permissionIds }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: rolesKeys.all });
      queryClient.invalidateQueries({ queryKey: ["auth", "session"] });
      queryClient.invalidateQueries({ queryKey: ["users"] });
    },
  });
}
