"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { notificationChannelsKeys } from "@/entities/notification-channel";
import { deleteNotificationChannel } from "../api/fetchers";
import { useToastMessage } from "@/shared/hooks/use-toast-message";

export function useDeleteNotificationChannel(projectId: string) {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("notifications");

  return useMutation({
    mutationFn: (id: string) => deleteNotificationChannel(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: notificationChannelsKeys.list(projectId) });
      success("channelDeleted");
    },
    onError: error,
  });
}
