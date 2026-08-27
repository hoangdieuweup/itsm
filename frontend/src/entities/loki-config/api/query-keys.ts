export const lokiConfigKeys = {
  all: ["loki-config"] as const,
  detail: (environmentId: string) => [...lokiConfigKeys.all, environmentId] as const,
};
