"use client";

import { useMutation } from "@tanstack/react-query";
import { testCloudflareAccountConnection } from "../api/fetchers";
import { useToastMessage } from "@/shared/hooks/use-toast-message";

export function useTestCloudflareAccountConnection() {
  const { success, error } = useToastMessage("cloudflareAccounts");

  return useMutation({
    mutationFn: (id: string) => testCloudflareAccountConnection(id),
    onSuccess: () => success("connectionOk"),
    onError: error,
  });
}
