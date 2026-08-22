"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createCloudflareConfig,
  deleteCloudflareConfig,
  fetchCloudflareConfigOrNull,
  updateCloudflareConfig,
} from "../api/fetchers";
import { cloudflareDnsKeys } from "../api/query-keys";

export function useCloudflareConfigQuery(environmentId: string) {
  return useQuery({
    queryKey: cloudflareDnsKeys.config(environmentId),
    queryFn: () => fetchCloudflareConfigOrNull(environmentId),
  });
}

export function useCreateCloudflareConfig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createCloudflareConfig,
    onSuccess: (config) => {
      queryClient.invalidateQueries({ queryKey: cloudflareDnsKeys.config(config.environmentId) });
    },
  });
}

export function useUpdateCloudflareConfig(environmentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (zoneId: string) => updateCloudflareConfig(environmentId, zoneId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareDnsKeys.config(environmentId) });
    },
  });
}

export function useDeleteCloudflareConfig(environmentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => deleteCloudflareConfig(environmentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareDnsKeys.config(environmentId) });
    },
  });
}
