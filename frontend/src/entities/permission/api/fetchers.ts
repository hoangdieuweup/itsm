import { apiFetch } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";
import { projectPermissionSetSchema } from "../model/schema";

export async function fetchProjectPermissions(projectId: string): Promise<string[]> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.PROJECTS.PERMISSIONS(projectId));
  return projectPermissionSetSchema.parse(raw).permissions;
}
