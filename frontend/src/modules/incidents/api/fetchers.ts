import { apiFetch } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";
import { incidentSchema, type Incident } from "@/entities/incident";

export interface CreateManualIncidentValues {
  environmentId: string;
  category: string;
  severity: string;
  title: string;
}

export async function acknowledgeIncident(id: string): Promise<Incident> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.INCIDENTS.ACKNOWLEDGE(id), { method: "POST" });
  return incidentSchema.parse(raw);
}

export async function resolveIncident(id: string): Promise<Incident> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.INCIDENTS.RESOLVE(id), { method: "POST" });
  return incidentSchema.parse(raw);
}

export async function createManualIncident(data: CreateManualIncidentValues): Promise<Incident> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.INCIDENTS.ROOT, { method: "POST", data });
  return incidentSchema.parse(raw);
}
