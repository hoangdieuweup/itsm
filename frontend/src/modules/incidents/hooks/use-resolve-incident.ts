"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { incidentsKeys } from "@/entities/incident";
import { resolveIncident } from "../api/fetchers";

export function useResolveIncident() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => resolveIncident(id),
    onSuccess: (incident) => {
      queryClient.invalidateQueries({ queryKey: incidentsKeys.all });
      queryClient.invalidateQueries({ queryKey: incidentsKeys.detail(incident.id) });
    },
  });
}
