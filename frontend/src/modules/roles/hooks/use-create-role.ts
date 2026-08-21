"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createRole } from "../api/fetchers";
import { rolesKeys } from "../api/query-keys";

export function useCreateRole() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      name,
      permissionIds,
    }: {
      name: string;
      permissionIds: number[];
    }) => createRole(name, permissionIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: rolesKeys.all });
      queryClient.invalidateQueries({ queryKey: ["auth", "session"] });
      queryClient.invalidateQueries({ queryKey: ["users"] });
    },
  });
}
