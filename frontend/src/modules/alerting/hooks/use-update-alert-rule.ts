"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { updateAlertRule, type AlertRuleFormValues } from "../api/fetchers";
import { alertRulesKeys } from "../api/query-keys";

interface UpdateAlertRuleInput {
  id: string;
  data: Partial<Pick<AlertRuleFormValues, "name" | "severity" | "channelIds">> & { isActive?: boolean };
}

export function useUpdateAlertRule(environmentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: UpdateAlertRuleInput) => updateAlertRule(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: alertRulesKeys.list(environmentId) });
    },
  });
}
