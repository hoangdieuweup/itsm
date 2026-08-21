import { apiFetch } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";
import type { Project } from "@/entities/project";
import type { Environment } from "@/entities/environment";

export async function createProject(name: string, description?: string): Promise<Project> {
  return apiFetch<Project>(API_CONFIG.ENDPOINTS.PROJECTS.ROOT, {
    method: "POST",
    data: { name, description },
  });
}

export async function updateProject(
  id: string,
  data: { name?: string; description?: string },
): Promise<Project> {
  return apiFetch<Project>(API_CONFIG.ENDPOINTS.PROJECTS.DETAIL(id), { method: "PATCH", data });
}

export async function deleteProject(id: string): Promise<void> {
  await apiFetch<null>(API_CONFIG.ENDPOINTS.PROJECTS.DETAIL(id), { method: "DELETE" });
}

export async function createEnvironment(
  projectId: string,
  data: { type: string; name: string; baseUrl?: string },
): Promise<Environment> {
  return apiFetch<Environment>(API_CONFIG.ENDPOINTS.PROJECTS.ENVIRONMENTS(projectId), {
    method: "POST",
    data,
  });
}

export async function updateEnvironment(
  id: string,
  data: { name?: string; baseUrl?: string },
): Promise<Environment> {
  return apiFetch<Environment>(API_CONFIG.ENDPOINTS.PROJECTS.ENVIRONMENT_DETAIL(id), {
    method: "PATCH",
    data,
  });
}

export async function deleteEnvironment(id: string): Promise<void> {
  await apiFetch<null>(API_CONFIG.ENDPOINTS.PROJECTS.ENVIRONMENT_DETAIL(id), { method: "DELETE" });
}

export interface ProjectLink {
  id: string;
  projectId: string;
  type: "jira" | "git" | "other";
  name: string;
  url: string;
  isDefault: boolean;
}

export async function fetchProjectLinks(projectId: string): Promise<ProjectLink[]> {
  return apiFetch<ProjectLink[]>(API_CONFIG.ENDPOINTS.PROJECTS.LINKS(projectId));
}

export async function createProjectLink(
  projectId: string,
  data: { type: string; name: string; url: string },
): Promise<ProjectLink> {
  return apiFetch<ProjectLink>(API_CONFIG.ENDPOINTS.PROJECTS.LINKS(projectId), { method: "POST", data });
}

export async function updateProjectLink(
  id: string,
  data: { name?: string; url?: string },
): Promise<ProjectLink> {
  return apiFetch<ProjectLink>(API_CONFIG.ENDPOINTS.PROJECTS.LINK_DETAIL(id), { method: "PATCH", data });
}

export async function deleteProjectLink(id: string): Promise<void> {
  await apiFetch<null>(API_CONFIG.ENDPOINTS.PROJECTS.LINK_DETAIL(id), { method: "DELETE" });
}
