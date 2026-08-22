"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { removeCloudflareAccountManager } from "../api/fetchers";
import { cloudflareAccountManagersKeys } from "./use-cloudflare-account-managers";

export function useRemoveCloudflareAccountManager(accountId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (userId: string) => removeCloudflareAccountManager(accountId, userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareAccountManagersKeys.forAccount(accountId) });
    },
  });
}
