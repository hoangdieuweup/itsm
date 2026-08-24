export const cloudflareConfigKeys = {
  all: ["cloudflare-config"] as const,
  detail: (environmentId: string) => [...cloudflareConfigKeys.all, environmentId] as const,
};
