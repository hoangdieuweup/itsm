"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createRole } from "../api/fetchers";
import { rolesKeys } from "@/entities/role";
import { useToastMessage } from "@/shared/hooks/use-toast-message";


export function useCreateRole() {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("roles");

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
      success("created");
    },
    onError: error,
  });
}
