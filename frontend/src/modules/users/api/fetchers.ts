import { apiFetch } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";
import { userSchema, type User, type UserStatus } from "@/entities/user";

/**
 * Updates a user's status via PATCH /users/{user_id}/status.
 * Returns the updated User object validated via `userSchema`.
 */
export async function updateUserStatus(
  userId: string,
  status: UserStatus,
): Promise<User> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.USERS.STATUS(userId), {
    method: "PATCH",
    data: { status },
  });
  return userSchema.parse(raw);
}

/**
 * Assigns multiple roles to a user via PUT /rbac/users/{userId}/roles.
 */
export async function assignUserRoles(userId: string, roleIds: string[]): Promise<void> {
  await apiFetch<unknown>(API_CONFIG.ENDPOINTS.RBAC.USER_ROLES(userId), {
    method: "PUT",
    data: { roleIds },
  });
}
