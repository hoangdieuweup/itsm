"use client";

import { useMutation } from "@tanstack/react-query";
import { testSendNotificationChannel } from "../api/fetchers";

/**
 * No query invalidation — a test-send doesn't change the channel's own
 * data, same reasoning as Phase 6's useRunLogQuery never invalidating
 * anything either.
 */
export function useTestSendNotificationChannel() {
  return useMutation({
    mutationFn: ({ id, message }: { id: string; message?: string }) => testSendNotificationChannel(id, message),
  });
}
