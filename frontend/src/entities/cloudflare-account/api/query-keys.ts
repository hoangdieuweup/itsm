/**
 * Hierarchical query key factory for the cloudflare-account entity.
 */
export const cloudflareAccountsKeys = {
  all: ["cloudflare-accounts"] as const,
  lists: () => [...cloudflareAccountsKeys.all, "list"] as const,
  list: () => [...cloudflareAccountsKeys.lists()] as const,
  detail: (id: string) => [...cloudflareAccountsKeys.all, "detail", id] as const,
};
