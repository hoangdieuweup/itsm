"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { incidentsKeys } from "@/entities/incident";
import { createManualIncident, type CreateManualIncidentValues } from "../api/fetchers";
import { useToastMessage } from "@/shared/hooks/use-toast-message";

export function useCreateManualIncident() {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("incidents");

  return useMutation({
    mutationFn: (data: CreateManualIncidentValues) => createManualIncident(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: incidentsKeys.all });
      success("created");
    },
    onError: error,
  });
}
