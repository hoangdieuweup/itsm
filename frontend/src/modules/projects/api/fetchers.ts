import { apiFetch } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";
import { projectSchema, type Project } from "@/entities/project";
import { environmentSchema, type Environment } from "@/entities/environment";
import { permissionSchema, type PermissionItem } from "@/entities/role";
import {
  projectLinkSchema,
  projectMemberSchema,
  projectRoleSchema,
  type ProjectLink,
  type ProjectMember,
  type ProjectRole,
} from "../model/schema";

export async function createProject(name: string, description?: string): Promise<Project> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.PROJECTS.ROOT, {
    method: "POST",
    data: { name, description },
  });
  return projectSchema.parse(raw);
}

export async function updateProject(
  id: string,
  data: { name?: string; description?: string },
): Promise<Project> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.PROJECTS.DETAIL(id), { method: "PATCH", data });
  return projectSchema.parse(raw);
}

export async function deleteProject(id: string): Promise<void> {
  await apiFetch<null>(API_CONFIG.ENDPOINTS.PROJECTS.DETAIL(id), { method: "DELETE" });
}

export async function createEnvironment(
  projectId: string,
  data: { type: string; name: string; baseUrl?: string },
): Promise<Environment> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.PROJECTS.ENVIRONMENTS(projectId), {
    method: "POST",
    data,
  });
  return environmentSchema.parse(raw);
}

export async function updateEnvironment(
  id: string,
  data: { name?: string; baseUrl?: string },
): Promise<Environment> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.PROJECTS.ENVIRONMENT_DETAIL(id), {
    method: "PATCH",
    data,
  });
  return environmentSchema.parse(raw);
}

export async function deleteEnvironment(id: string): Promise<void> {
  await apiFetch<null>(API_CONFIG.ENDPOINTS.PROJECTS.ENVIRONMENT_DETAIL(id), { method: "DELETE" });
}

export async function fetchProjectLinks(projectId: string): Promise<ProjectLink[]> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.PROJECTS.LINKS(projectId));
  return projectLinkSchema.array().parse(raw);
}

export async function createProjectLink(
  projectId: string,
  data: { type: string; name: string; url: string },
): Promise<ProjectLink> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.PROJECTS.LINKS(projectId), { method: "POST", data });
  return projectLinkSchema.parse(raw);
}

export async function updateProjectLink(
  id: string,
  data: { name?: string; url?: string },
): Promise<ProjectLink> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.PROJECTS.LINK_DETAIL(id), { method: "PATCH", data });
  return projectLinkSchema.parse(raw);
}

export async function deleteProjectLink(id: string): Promise<void> {
  await apiFetch<null>(API_CONFIG.ENDPOINTS.PROJECTS.LINK_DETAIL(id), { method: "DELETE" });
}

export async function fetchProjectMembers(projectId: string): Promise<ProjectMember[]> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.PROJECTS.MEMBERS(projectId));
  return projectMemberSchema.array().parse(raw);
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

export async function fetchProjectRoles(projectId: string): Promise<ProjectRole[]> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.PROJECTS.ROLES(projectId));
  return projectRoleSchema.array().parse(raw);
}

export async function fetchAssignablePermissions(): Promise<PermissionItem[]> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.PROJECTS.ASSIGNABLE_PERMISSIONS());
  return permissionSchema.array().parse(raw);
}

export async function createProjectRole(
  projectId: string,
  data: { name: string; permissionIds: string[] },
): Promise<ProjectRole> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.PROJECTS.ROLES(projectId), { method: "POST", data });
  return projectRoleSchema.parse(raw);
}

export async function updateProjectRole(
  id: string,
  data: { name?: string; permissionIds?: string[] },
): Promise<ProjectRole> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.PROJECTS.ROLE_DETAIL(id), { method: "PATCH", data });
  return projectRoleSchema.parse(raw);
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
