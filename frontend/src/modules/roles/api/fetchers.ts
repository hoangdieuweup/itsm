import { apiFetch } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";
import {
  roleSchema,
  rolesPageSchema,
  permissionsListSchema,
  type Role,
  type RolesPage,
  type PermissionsList,
} from "../model/schema";

/**
 * Fetches paginated roles from GET /rbac/roles.
 */
export async function fetchRoles(limit = 50, offset = 0): Promise<RolesPage> {
  const raw = await apiFetch<unknown>(
    `${API_CONFIG.ENDPOINTS.RBAC.ROLES}?limit=${limit}&offset=${offset}`,
  );
  return rolesPageSchema.parse(raw);
}

/**
 * Fetches the fixed permission catalog from GET /rbac/permissions.
 */
export async function fetchPermissions(): Promise<PermissionsList> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.RBAC.PERMISSIONS);
  return permissionsListSchema.parse(raw);
}

/**
 * Creates a new custom role via POST /rbac/roles.
 */
export async function createRole(
  name: string,
  permissionIds: number[],
): Promise<Role> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.RBAC.ROLES, {
    method: "POST",
    data: { name, permissionIds },
  });
  return roleSchema.parse(raw);
}

/**
 * Updates a role via PATCH /rbac/roles/{roleId}.
 */
export async function updateRole(
  roleId: number,
  data: { name?: string; permissionIds?: number[] },
): Promise<Role> {
  const raw = await apiFetch<unknown>(
    API_CONFIG.ENDPOINTS.RBAC.ROLE_DETAIL(roleId),
    {
      method: "PATCH",
      data,
    },
  );
  return roleSchema.parse(raw);
}

/**
 * Deletes a custom role via DELETE /rbac/roles/{roleId}.
 */
export async function deleteRole(roleId: number): Promise<void> {
  await apiFetch<null>(API_CONFIG.ENDPOINTS.RBAC.ROLE_DETAIL(roleId), {
    method: "DELETE",
  });
}
