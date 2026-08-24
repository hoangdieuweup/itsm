"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { notificationChannelsKeys } from "@/entities/notification-channel";
import { updateNotificationChannel, type NotificationChannelFormValues } from "../api/fetchers";

export function useUpdateNotificationChannel(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: string;
      data: Partial<Pick<NotificationChannelFormValues, "name" | "config">> & { isActive?: boolean };
    }) => updateNotificationChannel(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: notificationChannelsKeys.list(projectId) });
    },
  });
}
