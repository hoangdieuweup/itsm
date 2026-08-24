"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createAlertRule, type AlertRuleFormValues } from "../api/fetchers";
import { alertRulesKeys } from "../api/query-keys";

export function useCreateAlertRule(environmentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: AlertRuleFormValues) => createAlertRule(environmentId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: alertRulesKeys.list(environmentId) });
    },
  });
}
