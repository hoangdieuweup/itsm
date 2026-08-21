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
 * Assigns multiple roles to a user via PUT /rbac/users/{userId}/roles.
 */
export async function assignUserRoles(
  userId: string,
  roleIds: string[],
): Promise<void> {
  await apiFetch<unknown>(API_CONFIG.ENDPOINTS.RBAC.USER_ROLES(userId), {
    method: "PUT",
    data: { roleIds },
  });
}

/**
 * Fetches assigned roles for a user via GET /rbac/users/{userId}/roles.
 */
export async function fetchUserRoles(userId: string): Promise<Role[]> {
  const raw = await apiFetch<unknown>(
    API_CONFIG.ENDPOINTS.RBAC.USER_ROLES(userId),
  );
  return roleSchema.array().parse(raw);
}
