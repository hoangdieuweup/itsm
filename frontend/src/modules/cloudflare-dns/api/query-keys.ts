/**
 * Hierarchical query key factory for the cloudflare-dns module.
 */
export const cloudflareDnsKeys = {
  all: ["cloudflare-dns"] as const,
  zones: (accountId: string) => [...cloudflareDnsKeys.all, "zones", accountId] as const,
  config: (environmentId: string) => [...cloudflareDnsKeys.all, "config", environmentId] as const,
  records: (environmentId: string) => [...cloudflareDnsKeys.all, "records", environmentId] as const,
};
