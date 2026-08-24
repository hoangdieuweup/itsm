"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { cloudflareConfigKeys } from "@/entities/cloudflare-config";
import { createCloudflareConfig, deleteCloudflareConfig, updateCloudflareConfig } from "../api/fetchers";

export function useCreateCloudflareConfig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createCloudflareConfig,
    onSuccess: (config) => {
      queryClient.invalidateQueries({ queryKey: cloudflareConfigKeys.detail(config.environmentId) });
    },
  });
}

export function useUpdateCloudflareConfig(environmentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (zoneId: string) => updateCloudflareConfig(environmentId, zoneId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareConfigKeys.detail(environmentId) });
    },
  });
}

export function useDeleteCloudflareConfig(environmentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => deleteCloudflareConfig(environmentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareConfigKeys.detail(environmentId) });
    },
  });
}
