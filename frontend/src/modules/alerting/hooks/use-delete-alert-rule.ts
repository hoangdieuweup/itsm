"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deleteAlertRule } from "../api/fetchers";
import { alertRulesKeys } from "../api/query-keys";

export function useDeleteAlertRule(environmentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteAlertRule(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: alertRulesKeys.list(environmentId) });
    },
  });
}
