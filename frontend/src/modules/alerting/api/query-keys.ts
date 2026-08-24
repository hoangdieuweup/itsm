export const alertRulesKeys = {
  all: ["alert-rules"] as const,
  list: (environmentId: string) => [...alertRulesKeys.all, "list", environmentId] as const,
  availableAlerts: (accountId: string) => [...alertRulesKeys.all, "available-alerts", accountId] as const,
};
