"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { incidentsKeys } from "@/entities/incident";
import { createManualIncident, type CreateManualIncidentValues } from "../api/fetchers";

export function useCreateManualIncident() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateManualIncidentValues) => createManualIncident(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: incidentsKeys.all });
    },
  });
}
