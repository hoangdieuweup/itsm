"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deleteCloudflareAccount } from "../api/fetchers";
import { cloudflareAccountsKeys } from "@/entities/cloudflare-account";

export function useDeleteCloudflareAccount() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => deleteCloudflareAccount(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareAccountsKeys.all });
    },
  });
}
