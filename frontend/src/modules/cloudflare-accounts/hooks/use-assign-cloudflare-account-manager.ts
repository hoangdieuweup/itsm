"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { assignCloudflareAccountManager, type AccessLevel } from "../api/fetchers";
import { cloudflareAccountManagersKeys } from "./use-cloudflare-account-managers";

export function useAssignCloudflareAccountManager(accountId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: { userId: string; accessLevel: AccessLevel }) =>
      assignCloudflareAccountManager(accountId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareAccountManagersKeys.forAccount(accountId) });
    },
  });
}
