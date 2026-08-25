"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createLokiConfig,
  deleteLokiConfig,
  fetchLokiConfigOrNull,
  updateLokiConfig,
  type LokiConfigFormValues,
} from "../api/fetchers";
import { logViewerKeys } from "../api/query-keys";
import { useToastMessage } from "@/shared/hooks/use-toast-message";

export function useLokiConfigQuery(environmentId: string) {
  return useQuery({
    queryKey: logViewerKeys.lokiConfig(environmentId),
    queryFn: () => fetchLokiConfigOrNull(environmentId),
  });
}

export function useCreateLokiConfig(environmentId: string) {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("logViewer");

  return useMutation({
    mutationFn: (data: LokiConfigFormValues) => createLokiConfig(environmentId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: logViewerKeys.lokiConfig(environmentId) });
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
      queryClient.invalidateQueries({ queryKey: logViewerKeys.lokiConfig(environmentId) });
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
      queryClient.invalidateQueries({ queryKey: logViewerKeys.lokiConfig(environmentId) });
      success("configDeleted");
    },
    onError: error,
  });
}
