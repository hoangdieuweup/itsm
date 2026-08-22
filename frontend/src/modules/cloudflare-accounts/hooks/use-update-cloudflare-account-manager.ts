"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { updateCloudflareAccountManager, type AccessLevel } from "../api/fetchers";
import { cloudflareAccountManagersKeys } from "./use-cloudflare-account-managers";

export function useUpdateCloudflareAccountManager(accountId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ userId, accessLevel }: { userId: string; accessLevel: AccessLevel }) =>
      updateCloudflareAccountManager(accountId, userId, { accessLevel }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareAccountManagersKeys.forAccount(accountId) });
    },
  });
}
