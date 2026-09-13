"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { AccessLevel } from "@/shared/constants/cloudflare";
import { assignCloudflareAccountManager } from "../api/fetchers";
import { cloudflareAccountManagersKeys } from "./use-cloudflare-account-managers";
import { useToastMessage } from "@/shared/hooks/use-toast-message";

export function useAssignCloudflareAccountManager(accountId: string) {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("cloudflareAccounts");

  return useMutation({
    mutationFn: (data: { userId: string; accessLevel: AccessLevel }) =>
      assignCloudflareAccountManager(accountId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareAccountManagersKeys.forAccount(accountId) });
      success("managerAssigned");
    },
    onError: error,
  });
}
