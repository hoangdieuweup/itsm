"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { updateCloudflareAccount } from "../api/fetchers";
import { cloudflareAccountsKeys } from "@/entities/cloudflare-account";

export function useUpdateCloudflareAccount() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: { label?: string; apiToken?: string } }) =>
      updateCloudflareAccount(id, data),
    onSuccess: (_result, variables) => {
      queryClient.invalidateQueries({ queryKey: cloudflareAccountsKeys.all });
      queryClient.invalidateQueries({ queryKey: cloudflareAccountsKeys.detail(variables.id) });
    },
  });
}
