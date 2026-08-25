"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { cloudflareConfigKeys } from "@/entities/cloudflare-config";
import { createCloudflareConfig, deleteCloudflareConfig, updateCloudflareConfig } from "../api/fetchers";
import { useToastMessage } from "@/shared/hooks/use-toast-message";

export function useCreateCloudflareConfig() {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("cloudflareDns");

  return useMutation({
    mutationFn: createCloudflareConfig,
    onSuccess: (config) => {
      queryClient.invalidateQueries({ queryKey: cloudflareConfigKeys.detail(config.environmentId) });
      success("configCreated");
    },
    onError: error,
  });
}

export function useUpdateCloudflareConfig(environmentId: string) {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("cloudflareDns");

  return useMutation({
    mutationFn: (zoneId: string) => updateCloudflareConfig(environmentId, zoneId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareConfigKeys.detail(environmentId) });
      success("configUpdated");
    },
    onError: error,
  });
}

export function useDeleteCloudflareConfig(environmentId: string) {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("cloudflareDns");

  return useMutation({
    mutationFn: () => deleteCloudflareConfig(environmentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareConfigKeys.detail(environmentId) });
      success("configDeleted");
    },
    onError: error,
  });
}
