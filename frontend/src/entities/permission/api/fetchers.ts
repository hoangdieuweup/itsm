import { apiFetch } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";

export async function fetchProjectPermissions(projectId: string): Promise<string[]> {
  const data = await apiFetch<{ projectId: string; permissions: string[] }>(
    API_CONFIG.ENDPOINTS.PROJECTS.PERMISSIONS(projectId),
  );
  return data.permissions;
}
