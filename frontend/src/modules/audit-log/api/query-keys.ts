export const auditLogsKeys = {
  all: ["audit-logs"] as const,
  list: (filters?: Record<string, string | number | undefined>) =>
    [...auditLogsKeys.all, "list", filters] as const,
};
