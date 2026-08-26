/**
 * Hierarchical query key factory for the cloudflare-account entity.
 */
export const cloudflareAccountsKeys = {
  all: ["cloudflare-accounts"] as const,
  lists: () => [...cloudflareAccountsKeys.all, "list"] as const,
  list: () => [...cloudflareAccountsKeys.lists()] as const,
  detail: (id: string) => [...cloudflareAccountsKeys.all, "detail", id] as const,
  tunnels: (id: string) => [...cloudflareAccountsKeys.all, "tunnels", id] as const,
  zones: (id: string) => [...cloudflareAccountsKeys.all, "zones", id] as const,
  zoneDnsRecords: (id: string, zoneId: string) =>
    [...cloudflareAccountsKeys.all, "zones", id, "dns-records", zoneId] as const,
};
