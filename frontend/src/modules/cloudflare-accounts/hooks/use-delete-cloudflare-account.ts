"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deleteCloudflareAccount } from "../api/fetchers";
import { cloudflareAccountsKeys } from "@/entities/cloudflare-account";
import { useToastMessage } from "@/shared/hooks/use-toast-message";

export function useDeleteCloudflareAccount() {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("cloudflareAccounts");

  return useMutation({
    mutationFn: (id: string) => deleteCloudflareAccount(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareAccountsKeys.all });
      success("deleted");
    },
    onError: error,
  });
}
