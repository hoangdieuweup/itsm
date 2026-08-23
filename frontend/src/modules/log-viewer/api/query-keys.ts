export const logViewerKeys = {
  all: ["log-viewer"] as const,
  lokiConfig: (environmentId: string) => [...logViewerKeys.all, "loki-config", environmentId] as const,
  cloudflareAuditLogs: (environmentId: string, since?: string, before?: string) =>
    [...logViewerKeys.all, "cloudflare-audit-logs", environmentId, since ?? null, before ?? null] as const,
};
