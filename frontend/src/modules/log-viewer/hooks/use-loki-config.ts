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

export function useLokiConfigQuery(environmentId: string) {
  return useQuery({
    queryKey: logViewerKeys.lokiConfig(environmentId),
    queryFn: () => fetchLokiConfigOrNull(environmentId),
  });
}

export function useCreateLokiConfig(environmentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: LokiConfigFormValues) => createLokiConfig(environmentId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: logViewerKeys.lokiConfig(environmentId) });
    },
  });
}

export function useUpdateLokiConfig(environmentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: Partial<LokiConfigFormValues>) => updateLokiConfig(environmentId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: logViewerKeys.lokiConfig(environmentId) });
    },
  });
}

export function useDeleteLokiConfig(environmentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => deleteLokiConfig(environmentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: logViewerKeys.lokiConfig(environmentId) });
    },
  });
}
