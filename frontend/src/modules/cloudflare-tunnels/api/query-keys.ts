/**
 * Hierarchical query key factory for the cloudflare-tunnels module.
 */
export const cloudflareTunnelsKeys = {
  all: ["cloudflare-tunnels"] as const,
  list: (environmentId: string) => [...cloudflareTunnelsKeys.all, "list", environmentId] as const,
  hostnames: (environmentId: string, tunnelId: string) =>
    [...cloudflareTunnelsKeys.all, "hostnames", environmentId, tunnelId] as const,
};
