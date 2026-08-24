import { apiFetch } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";
import { incidentSchema, type Incident } from "../model/schema";

export async function fetchIncidents(filters: {
  projectId?: string;
  environmentId?: string;
  status?: string;
}): Promise<Incident[]> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.INCIDENTS.ROOT, { params: filters });
  return incidentSchema.array().parse(raw);
}

export async function fetchIncident(id: string): Promise<Incident> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.INCIDENTS.DETAIL(id));
  return incidentSchema.parse(raw);
}
