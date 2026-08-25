"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createTunnel,
  deleteTunnel,
  fetchTunnels,
  refreshTunnelStatus,
  revealTunnelToken,
  syncTunnels,
} from "../api/fetchers";
import { cloudflareTunnelsKeys } from "../api/query-keys";
import { useToastMessage } from "@/shared/hooks/use-toast-message";

export function useTunnelsQuery(environmentId: string) {
  return useQuery({
    queryKey: cloudflareTunnelsKeys.list(environmentId),
    queryFn: () => fetchTunnels(environmentId),
  });
}

export function useCreateTunnel(environmentId: string) {
  const queryClient = useQueryClient();
  const { error } = useToastMessage("cloudflareTunnels");

  return useMutation({
    mutationFn: (name: string) => createTunnel(environmentId, name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareTunnelsKeys.list(environmentId) });
    },
    onError: error,
  });
}

export function useDeleteTunnel(environmentId: string) {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("cloudflareTunnels");

  return useMutation({
    mutationFn: (tunnelId: string) => deleteTunnel(environmentId, tunnelId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareTunnelsKeys.list(environmentId) });
      success("deleted");
    },
    onError: error,
  });
}

export function useRevealTunnelToken(environmentId: string) {
  const { error } = useToastMessage("cloudflareTunnels");

  return useMutation({
    mutationFn: (tunnelId: string) => revealTunnelToken(environmentId, tunnelId),
    onError: error,
  });
}

export function useRefreshTunnelStatus(environmentId: string) {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("cloudflareTunnels");

  return useMutation({
    mutationFn: (tunnelId: string) => refreshTunnelStatus(environmentId, tunnelId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareTunnelsKeys.list(environmentId) });
      success("statusRefreshed");
    },
    onError: error,
  });
}

export function useSyncTunnels(environmentId: string) {
  const queryClient = useQueryClient();
  const { error } = useToastMessage("cloudflareTunnels");

  return useMutation({
    mutationFn: () => syncTunnels(environmentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareTunnelsKeys.list(environmentId) });
    },
    onError: error,
  });
}
