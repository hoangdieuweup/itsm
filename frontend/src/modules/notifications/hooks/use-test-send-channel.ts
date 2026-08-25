"use client";

import { useMutation } from "@tanstack/react-query";
import { testSendNotificationChannel } from "../api/fetchers";
import { useToastMessage } from "@/shared/hooks/use-toast-message";

/**
 * No query invalidation — a test-send doesn't change the channel's own
 * data, same reasoning as Phase 6's useRunLogQuery never invalidating
 * anything either.
 */
export function useTestSendNotificationChannel() {
  const { success, error } = useToastMessage("notifications");

  return useMutation({
    mutationFn: ({ id, message }: { id: string; message?: string }) => testSendNotificationChannel(id, message),
    onSuccess: () => success("testSent"),
    onError: error,
  });
}
