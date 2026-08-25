"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { updateRole } from "../api/fetchers";
import { rolesKeys } from "@/entities/role";
import { usersKeys } from "@/entities/user";
import { authKeys } from "@/entities/auth";
import { useToastMessage } from "@/shared/hooks/use-toast-message";


export function useUpdateRole() {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("roles");

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
      queryClient.invalidateQueries({ queryKey: authKeys.session() });
      queryClient.invalidateQueries({ queryKey: usersKeys.all });
      success("updated");
    },
    onError: error,
  });
}
