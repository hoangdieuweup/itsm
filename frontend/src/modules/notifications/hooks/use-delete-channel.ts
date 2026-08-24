"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { notificationChannelsKeys } from "@/entities/notification-channel";
import { deleteNotificationChannel } from "../api/fetchers";

export function useDeleteNotificationChannel(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteNotificationChannel(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: notificationChannelsKeys.list(projectId) });
    },
  });
}
