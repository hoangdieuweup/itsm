"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deleteRole } from "../api/fetchers";
import { rolesKeys } from "@/entities/role";
import { usersKeys } from "@/entities/user";
import { authKeys } from "@/entities/auth";
import { useToastMessage } from "@/shared/hooks/use-toast-message";


export function useDeleteRole() {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("roles");

  return useMutation({
    mutationFn: (roleId: string) => deleteRole(roleId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: rolesKeys.all });
      queryClient.invalidateQueries({ queryKey: authKeys.session() });
      queryClient.invalidateQueries({ queryKey: usersKeys.all });
      success("deleted");
    },
    onError: error,
  });
}
