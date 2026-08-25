"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { incidentsKeys } from "@/entities/incident";
import { resolveIncident } from "../api/fetchers";
import { useToastMessage } from "@/shared/hooks/use-toast-message";

export function useResolveIncident() {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("incidents");

  return useMutation({
    mutationFn: (id: string) => resolveIncident(id),
    onSuccess: (incident) => {
      queryClient.invalidateQueries({ queryKey: incidentsKeys.all });
      queryClient.invalidateQueries({ queryKey: incidentsKeys.detail(incident.id) });
      success("resolved");
    },
    onError: error,
  });
}
