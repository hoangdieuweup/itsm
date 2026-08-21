"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { updateRole } from "../api/fetchers";
import { rolesKeys } from "@/entities/role";


export function useUpdateRole() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      roleId,
      name,
      permissionIds,
    }: {
      roleId: string;
      name?: string;
      permissionIds?: string[];
    }) => updateRole(roleId, { name, permissionIds }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: rolesKeys.all });
      queryClient.invalidateQueries({ queryKey: ["auth", "session"] });
      queryClient.invalidateQueries({ queryKey: ["users"] });
    },
  });
}
