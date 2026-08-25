"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createAlertRule, type AlertRuleFormValues } from "../api/fetchers";
import { alertRulesKeys } from "../api/query-keys";
import { useToastMessage } from "@/shared/hooks/use-toast-message";

export function useCreateAlertRule(environmentId: string) {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("alerting");

  return useMutation({
    mutationFn: (data: AlertRuleFormValues) => createAlertRule(environmentId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: alertRulesKeys.list(environmentId) });
      success("ruleCreated");
    },
    onError: error,
  });
}
