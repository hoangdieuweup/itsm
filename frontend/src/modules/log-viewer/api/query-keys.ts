export const logViewerKeys = {
  all: ["log-viewer"] as const,
  cloudflareTrafficStats: (environmentId: string, since?: string, until?: string) =>
    [...logViewerKeys.all, "cloudflare-traffic-stats", environmentId, since ?? null, until ?? null] as const,
};
