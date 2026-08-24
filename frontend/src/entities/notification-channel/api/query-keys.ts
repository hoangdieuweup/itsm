export const notificationChannelsKeys = {
  all: ["notification-channels"] as const,
  list: (projectId: string, environmentId?: string) =>
    [...notificationChannelsKeys.all, "list", projectId, environmentId ?? null] as const,
  detail: (id: string) => [...notificationChannelsKeys.all, "detail", id] as const,
};
