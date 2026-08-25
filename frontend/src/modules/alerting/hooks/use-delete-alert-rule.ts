"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deleteAlertRule } from "../api/fetchers";
import { alertRulesKeys } from "../api/query-keys";
import { useToastMessage } from "@/shared/hooks/use-toast-message";

export function useDeleteAlertRule(environmentId: string) {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("alerting");

  return useMutation({
    mutationFn: (id: string) => deleteAlertRule(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: alertRulesKeys.list(environmentId) });
      success("ruleDeleted");
    },
    onError: error,
  });
}
