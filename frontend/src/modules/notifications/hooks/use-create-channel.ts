"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { notificationChannelsKeys } from "@/entities/notification-channel";
import { createNotificationChannel, type NotificationChannelFormValues } from "../api/fetchers";
import { useToastMessage } from "@/shared/hooks/use-toast-message";

export function useCreateNotificationChannel(projectId: string) {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("notifications");

  return useMutation({
    mutationFn: (data: NotificationChannelFormValues) => createNotificationChannel(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: notificationChannelsKeys.list(projectId) });
      success("channelCreated");
    },
    onError: error,
  });
}
