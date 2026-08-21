"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deleteRole } from "../api/fetchers";
import { rolesKeys } from "../api/query-keys";

export function useDeleteRole() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (roleId: number) => deleteRole(roleId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: rolesKeys.all });
      queryClient.invalidateQueries({ queryKey: ["auth", "session"] });
      queryClient.invalidateQueries({ queryKey: ["users"] });
    },
  });
}
