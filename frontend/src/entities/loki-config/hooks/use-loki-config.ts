"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchLokiConfigOrNull } from "../api/fetchers";
import { lokiConfigKeys } from "../api/query-keys";

export function useLokiConfigQuery(environmentId: string) {
  return useQuery({
    queryKey: lokiConfigKeys.detail(environmentId),
    queryFn: () => fetchLokiConfigOrNull(environmentId),
  });
}
