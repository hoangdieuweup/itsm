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

export function useTunnelsQuery(environmentId: string) {
  return useQuery({
    queryKey: cloudflareTunnelsKeys.list(environmentId),
    queryFn: () => fetchTunnels(environmentId),
  });
}

export function useCreateTunnel(environmentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => createTunnel(environmentId, name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareTunnelsKeys.list(environmentId) });
    },
  });
}

export function useDeleteTunnel(environmentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (tunnelId: string) => deleteTunnel(environmentId, tunnelId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareTunnelsKeys.list(environmentId) });
    },
  });
}

export function useRevealTunnelToken(environmentId: string) {
  return useMutation({
    mutationFn: (tunnelId: string) => revealTunnelToken(environmentId, tunnelId),
  });
}

export function useRefreshTunnelStatus(environmentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (tunnelId: string) => refreshTunnelStatus(environmentId, tunnelId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareTunnelsKeys.list(environmentId) });
    },
  });
}

export function useSyncTunnels(environmentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => syncTunnels(environmentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareTunnelsKeys.list(environmentId) });
    },
  });
}

