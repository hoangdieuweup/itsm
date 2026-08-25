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

export interface ProjectMember {
  userId: string;
  name: string;
  email: string;
  createdAt: string;
  projectRoleId?: string | null;
  projectRoleName?: string | null;
}

export async function fetchProjectMembers(projectId: string): Promise<ProjectMember[]> {
  return apiFetch<ProjectMember[]>(API_CONFIG.ENDPOINTS.PROJECTS.MEMBERS(projectId));
}

export async function addProjectMember(projectId: string, userId: string): Promise<void> {
  await apiFetch<null>(API_CONFIG.ENDPOINTS.PROJECTS.MEMBERS(projectId), {
    method: "POST",
    data: { userId },
  });
}

export async function removeProjectMember(projectId: string, userId: string): Promise<void> {
  await apiFetch<null>(API_CONFIG.ENDPOINTS.PROJECTS.MEMBER_DETAIL(projectId, userId), {
    method: "DELETE",
  });
}

export interface ProjectRolePermissionItem {
  id: string;
  resource: string;
  action: string;
  descriptionKey: string;
}

export interface ProjectRole {
  id: string;
  projectId: string;
  name: string;
  permissions: ProjectRolePermissionItem[];
}

export async function fetchProjectRoles(projectId: string): Promise<ProjectRole[]> {
  return apiFetch<ProjectRole[]>(API_CONFIG.ENDPOINTS.PROJECTS.ROLES(projectId));
}

export async function fetchAssignablePermissions(): Promise<ProjectRolePermissionItem[]> {
  return apiFetch<ProjectRolePermissionItem[]>(API_CONFIG.ENDPOINTS.PROJECTS.ASSIGNABLE_PERMISSIONS());
}

export async function createProjectRole(
  projectId: string,
  data: { name: string; permissionIds: string[] },
): Promise<ProjectRole> {
  return apiFetch<ProjectRole>(API_CONFIG.ENDPOINTS.PROJECTS.ROLES(projectId), { method: "POST", data });
}

export async function updateProjectRole(
  id: string,
  data: { name?: string; permissionIds?: string[] },
): Promise<ProjectRole> {
  return apiFetch<ProjectRole>(API_CONFIG.ENDPOINTS.PROJECTS.ROLE_DETAIL(id), { method: "PATCH", data });
}

export async function deleteProjectRole(id: string): Promise<void> {
  await apiFetch<null>(API_CONFIG.ENDPOINTS.PROJECTS.ROLE_DETAIL(id), { method: "DELETE" });
}

export async function assignMemberProjectRole(
  projectId: string,
  userId: string,
  projectRoleId: string | null,
): Promise<void> {
  await apiFetch<null>(API_CONFIG.ENDPOINTS.PROJECTS.MEMBER_ROLE(projectId, userId), {
    method: "PUT",
    data: { projectRoleId },
  });
}
