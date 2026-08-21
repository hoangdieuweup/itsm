import { apiFetch } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";
import { projectSchema, projectsPageSchema, type Project, type ProjectsPage } from "../model/schema";

/**
 * Fetches paginated projects from GET /projects.
 */
export async function fetchProjects(limit = 50, offset = 0): Promise<ProjectsPage> {
  const raw = await apiFetch<unknown>(
    `${API_CONFIG.ENDPOINTS.PROJECTS.ROOT}?limit=${limit}&offset=${offset}`,
  );
  return projectsPageSchema.parse(raw);
}

/**
 * Fetches one project from GET /projects/{id}.
 */
export async function fetchProject(id: string): Promise<Project> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.PROJECTS.DETAIL(id));
  return projectSchema.parse(raw);
}
