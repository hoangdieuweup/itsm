"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createCloudflareAccount } from "../api/fetchers";
import { cloudflareAccountsKeys } from "@/entities/cloudflare-account";

export function useCreateCloudflareAccount() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: { label: string; cfAccountId: string; apiToken: string }) =>
      createCloudflareAccount(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareAccountsKeys.all });
    },
  });
}
