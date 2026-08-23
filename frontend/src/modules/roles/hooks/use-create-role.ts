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
      queryClient.invalidateQueries({ queryKey: rolesKeys.all });
    },
  });
}
