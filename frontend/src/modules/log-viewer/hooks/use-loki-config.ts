"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { lokiConfigKeys } from "@/entities/loki-config";
import { createLokiConfig, deleteLokiConfig, updateLokiConfig, type LokiConfigFormValues } from "../api/fetchers";
import { useToastMessage } from "@/shared/hooks/use-toast-message";

export function useCreateLokiConfig(environmentId: string) {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("logViewer");

  return useMutation({
    mutationFn: (data: LokiConfigFormValues) => createLokiConfig(environmentId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: lokiConfigKeys.detail(environmentId) });
      success("configCreated");
    },
    onError: error,
  });
}

export function useUpdateLokiConfig(environmentId: string) {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("logViewer");

  return useMutation({
    mutationFn: (data: Partial<LokiConfigFormValues>) => updateLokiConfig(environmentId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: lokiConfigKeys.detail(environmentId) });
      success("configUpdated");
    },
    onError: error,
  });
}

export function useDeleteLokiConfig(environmentId: string) {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("logViewer");

  return useMutation({
    mutationFn: () => deleteLokiConfig(environmentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: lokiConfigKeys.detail(environmentId) });
      success("configDeleted");
    },
    onError: error,
  });
}
