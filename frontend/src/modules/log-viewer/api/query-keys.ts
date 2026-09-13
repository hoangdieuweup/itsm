import type { LogQueryValues } from "./fetchers";

export const logViewerKeys = {
  all: ["log-viewer"] as const,
  query: (environmentId: string, params: LogQueryValues) =>
    [...logViewerKeys.all, "query", environmentId, params] as const,
  cloudflareTrafficStats: (environmentId: string, since?: string, until?: string) =>
    [...logViewerKeys.all, "cloudflare-traffic-stats", environmentId, since ?? null, until ?? null] as const,
};
