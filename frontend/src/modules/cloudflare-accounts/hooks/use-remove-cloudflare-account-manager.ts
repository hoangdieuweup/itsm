"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { removeCloudflareAccountManager } from "../api/fetchers";
import { cloudflareAccountManagersKeys } from "./use-cloudflare-account-managers";
import { useToastMessage } from "@/shared/hooks/use-toast-message";

export function useRemoveCloudflareAccountManager(accountId: string) {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("cloudflareAccounts");

  return useMutation({
    mutationFn: (userId: string) => removeCloudflareAccountManager(accountId, userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareAccountManagersKeys.forAccount(accountId) });
      success("managerRemoved");
    },
    onError: error,
  });
}
