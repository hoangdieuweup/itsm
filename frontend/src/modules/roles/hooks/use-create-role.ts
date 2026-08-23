"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createRole } from "../api/fetchers";
import { rolesKeys } from "@/entities/role";


export function useCreateRole() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      name,
      permissionIds,
    }: {
      name: string;
      permissionIds: string[];
    }) => createRole(name, permissionIds),
    onSuccess: () => {
      // A newly created role isn't assigned to anyone yet, so unlike
      // update/delete, nothing about any user's displayed data or the
      // current session's own permission set can have gone stale.
      queryClient.invalidateQueries({ queryKey: rolesKeys.all });
    },
  });
}
