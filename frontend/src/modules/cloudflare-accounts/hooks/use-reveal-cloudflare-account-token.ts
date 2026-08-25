"use client";

import { useMutation } from "@tanstack/react-query";
import { revealCloudflareAccountToken } from "../api/fetchers";
import { useToastMessage } from "@/shared/hooks/use-toast-message";

export function useRevealCloudflareAccountToken() {
  const { error } = useToastMessage("cloudflareAccounts");

  return useMutation({
    mutationFn: (id: string) => revealCloudflareAccountToken(id),
    onError: error,
  });
}
