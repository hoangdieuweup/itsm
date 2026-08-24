"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchAlertRules, fetchAvailableAlerts } from "../api/fetchers";
import { alertRulesKeys } from "../api/query-keys";

export function useAlertRulesQuery(environmentId: string) {
  return useQuery({
    queryKey: alertRulesKeys.list(environmentId),
    queryFn: () => fetchAlertRules(environmentId),
  });
}

export function useAvailableAlertsQuery(accountId: string | null) {
  return useQuery({
    queryKey: alertRulesKeys.availableAlerts(accountId ?? ""),
    queryFn: () => fetchAvailableAlerts(accountId as string),
    enabled: Boolean(accountId),
  });
}
