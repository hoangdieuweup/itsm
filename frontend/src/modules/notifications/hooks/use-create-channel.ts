"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { notificationChannelsKeys } from "@/entities/notification-channel";
import { createNotificationChannel, type NotificationChannelFormValues } from "../api/fetchers";

export function useCreateNotificationChannel(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: NotificationChannelFormValues) => createNotificationChannel(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: notificationChannelsKeys.list(projectId) });
    },
  });
}
