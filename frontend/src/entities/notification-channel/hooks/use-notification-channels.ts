"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchNotificationChannels } from "../api/fetchers";
import { notificationChannelsKeys } from "../api/query-keys";

export function useNotificationChannelsQuery(projectId: string, environmentId?: string) {
  return useQuery({
    queryKey: notificationChannelsKeys.list(projectId, environmentId),
    queryFn: () => fetchNotificationChannels(projectId, environmentId),
  });
}
