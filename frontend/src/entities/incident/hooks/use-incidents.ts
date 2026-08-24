"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchIncident, fetchIncidents } from "../api/fetchers";
import { incidentsKeys } from "../api/query-keys";

export function useIncidentsQuery(filters: { projectId?: string; environmentId?: string; status?: string }) {
  return useQuery({ queryKey: incidentsKeys.list(filters), queryFn: () => fetchIncidents(filters) });
}

export function useIncidentQuery(id: string) {
  return useQuery({ queryKey: incidentsKeys.detail(id), queryFn: () => fetchIncident(id) });
}
