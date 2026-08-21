import { apiFetch } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";
import { roleSchema, type Role } from "@/entities/role";

/**
 * Creates a new custom role via POST /rbac/roles.
 */
export async function createRole(
  name: string,
  permissionIds: string[],
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
  roleId: string,
  data: { name?: string; permissionIds?: string[] },
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
export async function deleteRole(roleId: string): Promise<void> {
  await apiFetch<null>(API_CONFIG.ENDPOINTS.RBAC.ROLE_DETAIL(roleId), {
    method: "DELETE",
  });
}

