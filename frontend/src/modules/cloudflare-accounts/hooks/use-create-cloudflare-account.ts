"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createCloudflareAccount } from "../api/fetchers";
import { cloudflareAccountsKeys } from "@/entities/cloudflare-account";
import { useToastMessage } from "@/shared/hooks/use-toast-message";

export function useCreateCloudflareAccount() {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("cloudflareAccounts");

  return useMutation({
    mutationFn: (data: { label: string; cfAccountId: string; apiToken: string }) =>
      createCloudflareAccount(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareAccountsKeys.all });
      success("created");
    },
    onError: error,
  });
}
