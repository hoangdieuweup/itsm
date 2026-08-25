"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  addTunnelHostname,
  fetchTunnelHostnames,
  removeTunnelHostname,
  updateTunnelHostname,
} from "../api/fetchers";
import { cloudflareTunnelsKeys } from "../api/query-keys";
import { useToastMessage } from "@/shared/hooks/use-toast-message";

export function useTunnelHostnamesQuery(environmentId: string, tunnelId: string, enabled: boolean) {
  return useQuery({
    queryKey: cloudflareTunnelsKeys.hostnames(environmentId, tunnelId),
    queryFn: () => fetchTunnelHostnames(environmentId, tunnelId),
    enabled,
  });
}

export function useAddTunnelHostname(environmentId: string, tunnelId: string) {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("cloudflareTunnels");

  return useMutation({
    mutationFn: (data: { hostname: string; service: string }) =>
      addTunnelHostname(environmentId, tunnelId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareTunnelsKeys.hostnames(environmentId, tunnelId) });
      success("hostnameAdded");
    },
    onError: error,
  });
}

export function useUpdateTunnelHostname(environmentId: string, tunnelId: string) {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("cloudflareTunnels");

  return useMutation({
    mutationFn: ({ hostnameId, service }: { hostnameId: string; service: string }) =>
      updateTunnelHostname(environmentId, tunnelId, hostnameId, service),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareTunnelsKeys.hostnames(environmentId, tunnelId) });
      success("hostnameUpdated");
    },
    onError: error,
  });
}

export function useRemoveTunnelHostname(environmentId: string, tunnelId: string) {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("cloudflareTunnels");

  return useMutation({
    mutationFn: (hostnameId: string) => removeTunnelHostname(environmentId, tunnelId, hostnameId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareTunnelsKeys.hostnames(environmentId, tunnelId) });
      success("hostnameRemoved");
    },
    onError: error,
  });
}
