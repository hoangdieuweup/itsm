import { apiFetch } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";
import { environmentSchema, type Environment } from "../model/schema";

/**
 * Fetches all environments for a project from GET /projects/{projectId}/environments.
 */
export async function fetchProjectEnvironments(projectId: string): Promise<Environment[]> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.PROJECTS.ENVIRONMENTS(projectId));
  return environmentSchema.array().parse(raw);
}
